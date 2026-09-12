"""GET /stats - public usage counters for the website."""
import json

import usage

HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'OPTIONS,GET',
    'Cache-Control': 'public, max-age=60',
}


def handler(event, context):
    return {'statusCode': 200, 'headers': HEADERS, 'body': json.dumps(usage.snapshot())}
