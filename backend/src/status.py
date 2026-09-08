import boto3
import json
import os
from botocore.exceptions import ClientError

s3 = boto3.client('s3')
BUCKET_NAME = os.environ['STAGING_BUCKET']

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
}

def handler(event, context):
    # Handle CORS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': ''
        }

    request_id = event['pathParameters']['requestId']
    template_key = f"generated/{request_id}/template.yaml"

    try:
        # Check if object exists
        s3.head_object(Bucket=BUCKET_NAME, Key=template_key)

        # Plain regional URL: the generated/* prefix allows anonymous GET via
        # bucket policy. A presigned URL's session token (~1KB) overflows the
        # console sign-in redirect when embedded in a quick-create link, and
        # expires with the Lambda's role credentials.
        region = os.environ.get('AWS_REGION', 'us-east-1')
        template_url = f"https://{BUCKET_NAME}.s3.{region}.amazonaws.com/{template_key}"

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'status': 'READY',
                'templateUrl': template_url
            })
        }
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code not in ('404', 'NoSuchKey', 'NotFound'):
            # Real failure (permissions, throttling) — log it instead of
            # silently reporting PENDING forever.
            print(f"head_object failed for {template_key}: {e}")
        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'status': 'PENDING'
            })
        }
