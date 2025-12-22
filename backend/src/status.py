import boto3
import json
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

    request_id = event['pathParameters']['requestId']
    template_key = f"generated/{request_id}/template.yaml"
    
    try:
        # Check if object exists
        s3.head_object(Bucket=BUCKET_NAME, Key=template_key)
        
        # Generate presigned URL for the template (valid for 1 hour)
        template_url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': BUCKET_NAME, 'Key': template_key},
            ExpiresIn=3600
        )
        
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
            },
            'body': json.dumps({
                'status': 'READY',
                'templateUrl': template_url
            })
        }
    except:
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
            },
            'body': json.dumps({
                'status': 'PENDING'
            })
        }
