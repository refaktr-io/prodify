"""Custom::ContentDeployer handler. Runs in the site owner's account.

Create/Update: download the project zip, build it if it isn't pre-built,
sync the output into the site bucket, invalidate CloudFront on updates.
Delete: empty the bucket so CloudFormation can remove it.

Update is idempotent on SourceZipUrl. The URL of the last successful deploy
is recorded in .prodify/state.json inside the bucket, so a rollback to the
previous (long-expired) URL is a no-op instead of a second failure.
"""
import io
import json
import mimetypes
import os
import shutil
import subprocess
import traceback
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

import boto3

WORK_ROOT = '/tmp/project'
STATE_KEY = '.prodify/state.json'
SKIP_DIRS = {'node_modules', '__MACOSX', '.git'}
# Cloudflare/Netlify routing files that Nitro emits; meaningless on S3.
SKIP_FILES = {'_headers', '_redirects', '_routes.json'}
# Vite writes dist/, CRA writes build/, Nitro-based frameworks (TanStack
# Start) write .output/public/ - which only holds an index.html when
# prerendering is enabled; otherwise it's just assets for an SSR server.
OUTPUT_DIRS = ('dist', 'build', os.path.join('.output', 'public'))
TANSTACK_PRERENDER_HINT = (
    "This is a TanStack Start project (Lovable's current template); its build produces a server "
    "bundle, not a static site. In vite.config.ts add "
    "tanstackStart: { prerender: { enabled: true, crawlLinks: true, autoStaticPathsDiscovery: true } } "
    "and upload again - the build then writes a static site to .output/public."
)
BUILD_TIMEOUT_MARGIN_SECONDS = 90
MAX_REASON_CHARS = 1500

# Lambda's filesystem is read-only outside /tmp; package managers need writable
# caches. NODE_ENV must NOT be "production" here: npm and bun would then skip
# devDependencies, which is where vite and every other build tool lives.
BUILD_ENV = {
    **{k: v for k, v in os.environ.items() if k != 'NODE_ENV'},
    'HOME': '/tmp',
    'npm_config_cache': '/tmp/.npm',
    'BUN_INSTALL_CACHE_DIR': '/tmp/.bun-cache',
    'XDG_CACHE_HOME': '/tmp/.cache',
    'CI': 'true',
}

CONTENT_TYPES = {
    '.js': 'text/javascript',
    '.mjs': 'text/javascript',
    '.css': 'text/css',
    '.html': 'text/html',
    '.json': 'application/json',
    '.map': 'application/json',
    '.webmanifest': 'application/manifest+json',
    '.svg': 'image/svg+xml',
    '.ico': 'image/x-icon',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
    '.wasm': 'application/wasm',
    '.txt': 'text/plain',
    '.xml': 'application/xml',
}

s3 = boto3.client('s3')


# ---------------------------------------------------------------- CloudFormation plumbing

def send_response(event, context, status, data=None, physical_id=None, reason=None):
    body = json.dumps({
        'Status': status,
        'Reason': (reason or f"See CloudWatch log stream {context.log_stream_name}")[:MAX_REASON_CHARS],
        'PhysicalResourceId': physical_id or context.log_stream_name,
        'StackId': event['StackId'],
        'RequestId': event['RequestId'],
        'LogicalResourceId': event['LogicalResourceId'],
        'NoEcho': False,
        'Data': data or {},
    }).encode('utf-8')
    req = urllib.request.Request(
        event['ResponseURL'], data=body, method='PUT',
        headers={'content-type': '', 'content-length': str(len(body))},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"CloudFormation response: {resp.status}")
    except Exception as e:
        print(f"send_response failed: {e}")


class DeployError(Exception):
    """Failure with a message meant for the stack events, not just the logs."""


# ---------------------------------------------------------------- Bucket helpers

def list_keys(bucket):
    paginator = s3.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get('Contents', []):
            yield obj['Key']


def delete_keys(bucket, keys):
    keys = list(keys)
    for i in range(0, len(keys), 1000):
        chunk = [{'Key': k} for k in keys[i:i + 1000]]
        s3.delete_objects(Bucket=bucket, Delete={'Objects': chunk, 'Quiet': True})
    return len(keys)


def empty_bucket(bucket):
    try:
        deleted = delete_keys(bucket, list_keys(bucket))
        print(f"Deleted {deleted} objects from {bucket}")
    except s3.exceptions.NoSuchBucket:
        print(f"Bucket {bucket} already gone")


def read_state(bucket):
    try:
        return json.loads(s3.get_object(Bucket=bucket, Key=STATE_KEY)['Body'].read())
    except Exception:
        return {}


def write_state(bucket, state):
    s3.put_object(Bucket=bucket, Key=STATE_KEY, Body=json.dumps(state), ContentType='application/json')


# ---------------------------------------------------------------- Project handling

def download_and_extract(source_url):
    if os.path.exists(WORK_ROOT):
        shutil.rmtree(WORK_ROOT)
    os.makedirs(WORK_ROOT)

    print("Downloading project zip")
    try:
        with urllib.request.urlopen(source_url) as resp:
            content = resp.read()
    except urllib.error.HTTPError as e:
        if e.code in (403, 400):
            raise DeployError(
                "The source download link has expired (links are valid for ~2 hours). "
                "Upload the project to Prodify again and update the stack with the new template."
            ) from e
        raise DeployError(f"Could not download the project zip (HTTP {e.code})") from e

    print(f"Extracting {len(content)} bytes")
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        z.extractall(WORK_ROOT)

    # GitHub exports wrap everything in a single top-level folder.
    entries = [e for e in os.listdir(WORK_ROOT) if not e.startswith('.') and e != '__MACOSX']
    if len(entries) == 1 and os.path.isdir(os.path.join(WORK_ROOT, entries[0])):
        return os.path.join(WORK_ROOT, entries[0])
    return WORK_ROOT


def find_build_output(project_dir):
    """First conventional output directory that actually contains an index.html."""
    for name in OUTPUT_DIRS:
        candidate = os.path.join(project_dir, name)
        if os.path.isfile(os.path.join(candidate, 'index.html')):
            return candidate
    return None


def uses_package(project_dir, package_name):
    try:
        with open(os.path.join(project_dir, 'package.json')) as f:
            pkg = json.load(f)
    except (OSError, ValueError):
        return False
    return any(package_name in pkg.get(section, {}) for section in ('dependencies', 'devDependencies'))


def no_output_message(project_dir):
    if uses_package(project_dir, '@tanstack/react-start'):
        return TANSTACK_PRERENDER_HINT
    return "The build finished but produced no dist/, build/, or .output/public folder containing an index.html."


def run(cmd, cwd, timeout):
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, env=BUILD_ENV, capture_output=True, text=True, timeout=timeout)
    if result.stdout:
        print(result.stdout[-4000:])
    if result.returncode != 0:
        print(result.stderr[-4000:])
        tail = (result.stderr or result.stdout).strip().splitlines()[-8:]
        raise DeployError(f"`{' '.join(cmd)}` failed:\n" + '\n'.join(tail))
    return result


def build_project(project_dir, context):
    has_bun_lock = any(os.path.exists(os.path.join(project_dir, f)) for f in ('bun.lockb', 'bun.lock'))
    has_npm_lock = os.path.exists(os.path.join(project_dir, 'package-lock.json'))

    def remaining():
        return max(30, context.get_remaining_time_in_millis() // 1000 - BUILD_TIMEOUT_MARGIN_SECONDS)

    try:
        if has_bun_lock:
            run(['bun', 'install'], project_dir, remaining())
            run(['bun', 'run', 'build'], project_dir, remaining())
        else:
            # devDependencies hold the build tooling (vite etc.), so never --omit=dev.
            run(['npm', 'ci'] if has_npm_lock else ['npm', 'install', '--no-audit', '--no-fund'], project_dir, remaining())
            run(['npm', 'run', 'build'], project_dir, remaining())
    except subprocess.TimeoutExpired as e:
        raise DeployError(
            "The build ran out of time. Build the project locally and upload a zip that includes the dist/ folder."
        ) from e

    output = find_build_output(project_dir)
    if not output:
        raise DeployError(no_output_message(project_dir))
    return output


def content_type_for(filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext in CONTENT_TYPES:
        return CONTENT_TYPES[ext]
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or 'application/octet-stream'


def cache_control_for(key):
    if key.endswith('.html') or key in ('manifest.json', 'site.webmanifest', 'robots.txt', 'sitemap.xml'):
        return 'no-cache'
    if key.startswith('assets/'):
        # Vite content-hashes everything under assets/.
        return 'public, max-age=31536000, immutable'
    return 'public, max-age=3600'


def collect_files(deploy_dir):
    files = {}
    for root, dirs, names in os.walk(deploy_dir):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in SKIP_DIRS]
        for name in names:
            if name.startswith('.') or name in SKIP_FILES:
                continue
            path = os.path.join(root, name)
            key = os.path.relpath(path, deploy_dir).replace(os.sep, '/')
            files[key] = path
    return files


def sync_to_bucket(bucket, files):
    def upload(item):
        key, path = item
        with open(path, 'rb') as f:
            s3.put_object(
                Bucket=bucket, Key=key, Body=f.read(),
                ContentType=content_type_for(key), CacheControl=cache_control_for(key),
            )

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(upload, files.items()))
    print(f"Uploaded {len(files)} files")

    stale = [k for k in list_keys(bucket) if k not in files and not k.startswith('.prodify/')]
    if stale:
        print(f"Removed {delete_keys(bucket, stale)} stale files")


def invalidate(distribution_id, request_id):
    boto3.client('cloudfront').create_invalidation(
        DistributionId=distribution_id,
        InvalidationBatch={'Paths': {'Quantity': 1, 'Items': ['/*']}, 'CallerReference': request_id},
    )
    print(f"Invalidated distribution {distribution_id}")


def deploy(props, context):
    project_dir = download_and_extract(props['SourceZipUrl'])
    deploy_dir = find_build_output(project_dir)
    if deploy_dir:
        print(f"Using pre-built output at {os.path.relpath(deploy_dir, WORK_ROOT)}")
    elif os.path.exists(os.path.join(project_dir, 'package.json')):
        print("No build output in the zip; building")
        deploy_dir = build_project(project_dir, context)
    else:
        print("No package.json; deploying the zip contents as-is")
        deploy_dir = project_dir

    files = collect_files(deploy_dir)
    if 'index.html' not in files:
        raise DeployError("No index.html found at the top level of the deployable output.")
    sync_to_bucket(props['BucketName'], files)
    return len(files)


# ---------------------------------------------------------------- Entry point

def handler(event, context):
    props = event.get('ResourceProperties', {})
    bucket = props.get('BucketName', '')
    physical_id = f"prodify-content-{bucket}"
    request_type = event['RequestType']

    try:
        if request_type == 'Delete':
            if bucket:
                empty_bucket(bucket)
            send_response(event, context, 'SUCCESS', physical_id=physical_id)
            return

        if request_type == 'Update':
            state = read_state(bucket)
            if state.get('sourceZipUrl') == props.get('SourceZipUrl'):
                print("SourceZipUrl unchanged since last successful deploy; nothing to do")
                send_response(event, context, 'SUCCESS', {'UploadedFiles': state.get('uploadedFiles', 0)}, physical_id)
                return

        uploaded = deploy(props, context)
        write_state(bucket, {'sourceZipUrl': props['SourceZipUrl'], 'uploadedFiles': uploaded})

        if request_type == 'Update' and props.get('DistributionId'):
            invalidate(props['DistributionId'], event['RequestId'])

        shutil.rmtree(WORK_ROOT, ignore_errors=True)
        send_response(event, context, 'SUCCESS', {'UploadedFiles': uploaded}, physical_id)

    except DeployError as e:
        print(f"Deploy failed: {e}")
        send_response(event, context, 'FAILED', physical_id=physical_id, reason=str(e))
    except Exception as e:
        traceback.print_exc()
        send_response(event, context, 'FAILED', physical_id=physical_id, reason=f"{type(e).__name__}: {e}")
