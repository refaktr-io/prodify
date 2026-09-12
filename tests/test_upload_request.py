import json
from unittest.mock import patch

import upload_request


def test_upload_request_returns_presigned_url_and_counts_an_upload():
    with patch.object(upload_request, 's3') as s3, patch.object(upload_request.usage, 'record') as record:
        s3.generate_presigned_url.return_value = 'https://signed.example/put'
        resp = upload_request.handler({}, None)
    body = json.loads(resp['body'])
    assert body['uploadUrl'] == 'https://signed.example/put'
    assert body['key'] == f"uploads/{body['requestId']}/source.zip"
    assert body['maxUploadBytes'] == 50 * 1024 * 1024
    record.assert_called_once_with('uploads')
