import json
import os
import uuid

import boto3

s3 = boto3.client('s3')
BUCKET_NAME = os.environ['STAGING_BUCKET']
MAX_UPLOAD_BYTES = int(os.environ.get('MAX_UPLOAD_BYTES', 50 * 1024 * 1024))

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'OPTIONS,POST'
}


def handler(event, context):
    request_id = str(uuid.uuid4())
    key = f"uploads/{request_id}/source.zip"

    presigned_url = s3.generate_presigned_url(
        'put_object',
        Params={'Bucket': BUCKET_NAME, 'Key': key, 'ContentType': 'application/zip'},
        ExpiresIn=300
    )

    return {
        'statusCode': 200,
        'headers': CORS_HEADERS,
        'body': json.dumps({
            'uploadUrl': presigned_url,
            'requestId': request_id,
            'key': key,
            # Clients should check file size before uploading; the generator
            # rejects anything larger after the fact.
            'maxUploadBytes': MAX_UPLOAD_BYTES,
        })
    }
