import boto3
import urllib.request
import zipfile
import io
import json
import mimetypes
import subprocess
import os
import shutil

def send_response(event, context, response_status, response_data, physical_resource_id=None, reason=None):
    response_url = event['ResponseURL']
    response_body = {
        'Status': response_status,
        'Reason': reason or f'See CloudWatch Log Stream: {context.log_stream_name}',
        'PhysicalResourceId': physical_resource_id or context.log_stream_name,
        'StackId': event['StackId'],
        'RequestId': event['RequestId'],
        'LogicalResourceId': event['LogicalResourceId'],
        'NoEcho': False,
        'Data': response_data
    }
    json_response_body = json.dumps(response_body)
    headers = {
        'content-type': '',
        'content-length': str(len(json_response_body))
    }
    try:
        req = urllib.request.Request(response_url, data=json_response_body.encode('utf-8'), headers=headers, method='PUT')
        with urllib.request.urlopen(req) as response:
            print(f"Status code: {response.reason}")
    except Exception as e:
        print(f"send_response failed: {e}")

def handler(event, context):
    try:
        if event['RequestType'] == 'Delete':
            send_response(event, context, 'SUCCESS', {})
            return
        
        source_url = event['ResourceProperties']['SourceZipUrl']
        bucket = event['ResourceProperties']['BucketName']
        
        # Create working directory
        work_dir = '/tmp/project'
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir)
        os.makedirs(work_dir)
        
        print(f"Downloading from {source_url}")
        with urllib.request.urlopen(source_url) as response:
            zip_content = response.read()
        
        print("Extracting project...")
        with zipfile.ZipFile(io.BytesIO(zip_content)) as z:
            z.extractall(work_dir)
        
        # Detect if there's a root folder
        items = os.listdir(work_dir)
        items = [i for i in items if not i.startswith('.') and i != '__MACOSX']
        if len(items) == 1 and os.path.isdir(os.path.join(work_dir, items[0])):
            work_dir = os.path.join(work_dir, items[0])
        
        # Check if this is a Node.js project
        package_json_path = os.path.join(work_dir, 'package.json')
        needs_build = os.path.exists(package_json_path)
        
        deploy_dir = work_dir
        
        if needs_build:
            print("Detected Node.js project, checking for pre-built assets...")
            
            # Check if dist or build already exists
            dist_dir = os.path.join(work_dir, 'dist')
            build_dir = os.path.join(work_dir, 'build')
            
            if os.path.exists(dist_dir) and os.listdir(dist_dir):
                print("Found existing dist/ folder, using it")
                deploy_dir = dist_dir
            elif os.path.exists(build_dir) and os.listdir(build_dir):
                print("Found existing build/ folder, using it")
                deploy_dir = build_dir
            else:
                print("No pre-built assets found, building project...")
                
                # Check for package manager
                has_bun = os.path.exists(os.path.join(work_dir, 'bun.lockb'))
                
                try:
                    if has_bun:
                        print("Installing dependencies with Bun...")
                        result = subprocess.run(
                            ['bun', 'install'],
                            cwd=work_dir,
                            capture_output=True,
                            text=True,
                            timeout=600
                        )
                        print(result.stdout)
                        if result.returncode != 0:
                            print(f"bun install stderr: {result.stderr}")
                        
                        print("Building project with Bun...")
                        result = subprocess.run(
                            ['bun', 'run', 'build'],
                            cwd=work_dir,
                            capture_output=True,
                            text=True,
                            timeout=600
                        )
                        print(result.stdout)
                        if result.returncode != 0:
                            print(f"bun build stderr: {result.stderr}")
                            send_response(event, context, 'FAILED', {}, 
                                        reason=f"Build failed: {result.stderr}")
                            return
                    else:
                        print("Installing dependencies...")
                        result = subprocess.run(
                            ['npm', 'ci', '--omit=dev'],
                            cwd=work_dir,
                            capture_output=True,
                            text=True,
                            timeout=600
                        )
                        print(result.stdout)
                        if result.returncode != 0:
                            print(f"npm install stderr: {result.stderr}")
                        
                        print("Building project...")
                        result = subprocess.run(
                            ['npm', 'run', 'build'],
                        cwd=work_dir,
                        capture_output=True,
                        text=True,
                        timeout=600
                    )
                    print(result.stdout)
                    if result.returncode != 0:
                        print(f"npm build stderr: {result.stderr}")
                        raise Exception(f"Build failed: {result.stderr}")
                    
                    # Look for dist or build folder
                    if os.path.exists(dist_dir) and os.listdir(dist_dir):
                        deploy_dir = dist_dir
                        print("Using dist/ folder")
                    elif os.path.exists(build_dir) and os.listdir(build_dir):
                        deploy_dir = build_dir
                        print("Using build/ folder")
                    else:
                        raise Exception("No dist/ or build/ folder found after build")
                        
                except subprocess.TimeoutExpired:
                    send_response(event, context, 'FAILED', {},
                                reason="Build timed out (10 min limit). Please build locally and upload dist/ folder.")
                    return
                except Exception as e:
                    send_response(event, context, 'FAILED', {},
                                reason=f"Build failed: {str(e)}. Please build locally and upload dist/ folder.")
                    return
        
        print(f"Uploading from {deploy_dir}...")
        s3 = boto3.client('s3')
        
        uploaded_count = 0
        for root, dirs, files in os.walk(deploy_dir):
            # Remove hidden directories and node_modules from traversal
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__MACOSX' and d != 'node_modules']
            
            for filename in files:
                # Skip hidden files and macOS metadata
                if filename.startswith('.') or filename == '.DS_Store':
                    continue
                
                filepath = os.path.join(root, filename)
                relative_path = os.path.relpath(filepath, deploy_dir)
                
                # Skip if in hidden directory
                if any(part.startswith('.') or part == '__MACOSX' for part in relative_path.split(os.sep)):
                    continue
                
                content_type, _ = mimetypes.guess_type(filename)
                if not content_type:
                    content_type = 'application/octet-stream'
                
                with open(filepath, 'rb') as f:
                    s3.put_object(
                        Bucket=bucket,
                        Key=relative_path.replace('\\', '/'),
                        Body=f.read(),
                        ContentType=content_type
                    )
                uploaded_count += 1
                
                if uploaded_count % 10 == 0:
                    print(f"Uploaded {uploaded_count} files...")
        
        print(f"Successfully uploaded {uploaded_count} files")
        
        # Cleanup
        shutil.rmtree('/tmp/project', ignore_errors=True)
        
        send_response(event, context, 'SUCCESS', {})
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        send_response(event, context, 'FAILED', {}, reason=str(e))
