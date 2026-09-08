import json
import os

import boto3
from botocore.exceptions import ClientError

s3 = boto3.client('s3')
BUCKET_NAME = os.environ['STAGING_BUCKET']
REGION = os.environ.get('AWS_REGION', 'us-east-1')
# Regions the generated template can be deployed in (deployer image replicated
# there). Clients use this to build the console link: accounts from AWS's new
# sign-up experience are locked to one region (us-east-2 / eu-north-1 /
# ap-southeast-2) and can't create stacks in us-east-1.
SUPPORTED_REGIONS = [r.strip() for r in os.environ.get('DEPLOYER_IMAGE_REGIONS', 'us-east-1').split(',') if r.strip()]

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'OPTIONS,GET'
}


def respond(body):
    return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': json.dumps(body)}


def object_exists(key):
    try:
        s3.head_object(Bucket=BUCKET_NAME, Key=key)
        return True
    except ClientError as e:
        code = e.response.get('Error', {}).get('Code', '')
        if code in ('404', 'NoSuchKey', 'NotFound'):
            return False
        raise


def handler(event, context):
    request_id = (event.get('pathParameters') or {}).get('requestId', '')
    if not request_id or '/' in request_id:
        return {'statusCode': 400, 'headers': CORS_HEADERS, 'body': json.dumps({'message': 'invalid requestId'})}

    prefix = f"generated/{request_id}/"
    template_key = prefix + 'template.yaml'
    error_key = prefix + 'error.json'

    if object_exists(template_key):
        # Plain regional URL: the generated/* prefix allows anonymous GET via
        # bucket policy. A presigned URL's session token (~1KB) overflows the
        # console sign-in redirect when embedded in a quick-create link, and
        # expires with the Lambda's role credentials.
        return respond({
            'status': 'READY',
            'templateUrl': f"https://{BUCKET_NAME}.s3.{REGION}.amazonaws.com/{template_key}",
            'supportedRegions': SUPPORTED_REGIONS,
        })

    if object_exists(error_key):
        error = json.loads(s3.get_object(Bucket=BUCKET_NAME, Key=error_key)['Body'].read())
        return respond({'status': 'ERROR', 'message': error.get('message', 'Generation failed')})

    return respond({'status': 'PENDING'})
