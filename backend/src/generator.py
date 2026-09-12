"""S3-triggered: turns uploads/{requestId}/source.zip into generated/{requestId}/template.yaml.

Status for the frontend is derived from what exists under generated/{requestId}/:
template.yaml means READY, error.json means ERROR, neither means PENDING.
"""
import json
import os
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import boto3

import usage

s3 = boto3.client('s3')
BUCKET_NAME = os.environ['STAGING_BUCKET']
MAX_UPLOAD_BYTES = int(os.environ.get('MAX_UPLOAD_BYTES', 50 * 1024 * 1024))
SOURCE_URL_TTL_SECONDS = 7200

TEMPLATE_PATH = Path(__file__).parent / 'templates' / 'site-template.yaml'


def deployer_image_mappings(account_id, region_names, repository, digest):
    """YAML lines for the Mappings block and the region list for the Rules block."""
    lines = []
    for region in region_names:
        uri = f"{account_id}.dkr.ecr.{region}.amazonaws.com/{repository}@{digest}"
        lines.append(f"    {region}:")
        lines.append(f"      Uri: {uri}")
    return '\n'.join(lines)


def render_template(source_zip_url, account_id, region_names, repository, digest, generated_at=None):
    generated_at = generated_at or datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    template = TEMPLATE_PATH.read_text()
    return (
        template
        .replace('__GENERATED_AT__', generated_at)
        .replace('__SUPPORTED_REGIONS__', json.dumps(list(region_names)))
        .replace('__DEPLOYER_IMAGE_MAPPINGS__', deployer_image_mappings(account_id, region_names, repository, digest))
        .replace('__SOURCE_ZIP_URL__', source_zip_url)
    )


def write_error(request_id, message):
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=f"generated/{request_id}/error.json",
        Body=json.dumps({'status': 'ERROR', 'message': message}),
        ContentType='application/json',
    )


def handler(event, context):
    record = event['Records'][0]['s3']
    key = urllib.parse.unquote_plus(record['object']['key'], encoding='utf-8')
    size = record['object'].get('size', 0)

    parts = key.split('/')
    if len(parts) != 3 or parts[0] != 'uploads' or parts[2] != 'source.zip':
        print(f"Ignoring unexpected key {key}")
        return
    request_id = parts[1]

    if size > MAX_UPLOAD_BYTES:
        limit_mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        print(f"Rejecting {key}: {size} bytes exceeds {MAX_UPLOAD_BYTES}")
        s3.delete_object(Bucket=BUCKET_NAME, Key=key)
        write_error(request_id, f"Upload is larger than the {limit_mb} MB limit. Remove node_modules and build output from the zip and try again.")
        usage.record('rejected')
        return

    source_zip_url = s3.generate_presigned_url(
        'get_object',
        Params={'Bucket': BUCKET_NAME, 'Key': key},
        ExpiresIn=SOURCE_URL_TTL_SECONDS,
    )

    account_id = context.invoked_function_arn.split(':')[4]
    region_names = [r.strip() for r in os.environ['DEPLOYER_IMAGE_REGIONS'].split(',') if r.strip()]
    template = render_template(
        source_zip_url,
        account_id,
        region_names,
        os.environ['DEPLOYER_IMAGE_REPOSITORY'],
        os.environ['DEPLOYER_IMAGE_DIGEST'],
    )

    output_key = f"generated/{request_id}/template.yaml"
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=output_key,
        Body=template,
        ContentType='application/x-yaml',
    )
    usage.record('conversions')
    print(f"Generated {output_key} ({size} byte upload)")
