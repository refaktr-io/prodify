import boto3
import json
import uuid
import os

s3 = boto3.client('s3')
BUCKET_NAME = os.environ['STAGING_BUCKET']

def handler(event, context):
    # Handle CORS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
            },
            'body': ''
        }

    request_id = str(uuid.uuid4())
    key = f"uploads/{request_id}/source.zip"
    
    # Generate presigned URL for uploading
    presigned_url = s3.generate_presigned_url(
        'put_object',
        Params={'Bucket': BUCKET_NAME, 'Key': key, 'ContentType': 'application/zip'},
        ExpiresIn=300
    )
    
    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
        },
        'body': json.dumps({
            'uploadUrl': presigned_url,
            'requestId': request_id,
            'key': key
        })
    }
