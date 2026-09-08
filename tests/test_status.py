import json

from botocore.exceptions import ClientError
from unittest.mock import patch

import status


def not_found():
    return ClientError({'Error': {'Code': '404', 'Message': 'Not Found'}}, 'HeadObject')


def call(request_id):
    return json.loads(status.handler({'pathParameters': {'requestId': request_id}}, None)['body'])


def test_ready_returns_plain_regional_url():
    with patch.object(status, 's3') as s3:
        s3.head_object.return_value = {}
        body = call('abc')
    assert body['status'] == 'READY'
    assert body['templateUrl'] == 'https://test-staging-bucket.s3.us-east-1.amazonaws.com/generated/abc/template.yaml'
    assert 'X-Amz' not in body['templateUrl']
    assert body['supportedRegions'] == ['us-east-1', 'eu-west-1']


def test_pending_when_nothing_generated_yet():
    with patch.object(status, 's3') as s3:
        s3.head_object.side_effect = not_found()
        body = call('abc')
    assert body == {'status': 'PENDING'}


def test_error_marker_surfaces_message():
    with patch.object(status, 's3') as s3:
        s3.head_object.side_effect = [not_found(), {}]
        s3.get_object.return_value = {'Body': _Body(json.dumps({'status': 'ERROR', 'message': 'too big'}))}
        body = call('abc')
    assert body == {'status': 'ERROR', 'message': 'too big'}


def test_rejects_malformed_request_id():
    resp = status.handler({'pathParameters': {'requestId': '../other'}}, None)
    assert resp['statusCode'] == 400


class _Body:
    def __init__(self, text):
        self._text = text

    def read(self):
        return self._text.encode()
