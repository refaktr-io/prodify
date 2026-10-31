"""The S3NotificationFunction inline handler in the backend template.

It installs the generator trigger on the staging bucket. Its physical ID must
never change on Update: CloudFormation would follow a changed ID with a
cleanup Delete for the same bucket, which removes the live trigger.
"""
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from cfnlint.decode import decode

TEMPLATE = Path(__file__).parent.parent / 'backend' / 'infrastructure' / 'template.yaml'


@pytest.fixture
def handler(monkeypatch):
    template, errors = decode(str(TEMPLATE))
    assert not errors
    source = template['Resources']['S3NotificationFunction']['Properties']['Code']['ZipFile']

    s3 = MagicMock()
    sent = []
    cfnresponse = types.SimpleNamespace(
        SUCCESS='SUCCESS', FAILED='FAILED',
        send=lambda event, context, status, data, physical_id=None: sent.append((status, physical_id)),
    )
    monkeypatch.setitem(sys.modules, 'boto3', types.SimpleNamespace(client=lambda name: s3))
    monkeypatch.setitem(sys.modules, 'cfnresponse', cfnresponse)
    module = {}
    exec(compile(str(source), 'index.py', 'exec'), module)
    return module['handler'], s3, sent


def event(request_type, physical_id=None):
    e = {'RequestType': request_type, 'ResourceProperties': {'Bucket': 'staging', 'FunctionArn': 'arn:fn'}}
    if physical_id:
        e['PhysicalResourceId'] = physical_id
    return e


def test_create_uses_bucket_name_as_physical_id(handler):
    fn, s3, sent = handler
    fn(event('Create'), None)
    assert sent == [('SUCCESS', 'staging')]
    config = s3.put_bucket_notification_configuration.call_args.kwargs['NotificationConfiguration']
    assert config['LambdaFunctionConfigurations'][0]['LambdaFunctionArn'] == 'arn:fn'


@pytest.mark.parametrize('request_type', ['Update', 'Delete'])
def test_update_and_delete_echo_existing_physical_id(handler, request_type):
    fn, _, sent = handler
    fn(event(request_type, physical_id='2026/09/08/[$LATEST]abc'), None)
    assert sent == [('SUCCESS', '2026/09/08/[$LATEST]abc')]


def test_failure_keeps_physical_id(handler):
    fn, s3, sent = handler
    s3.put_bucket_notification_configuration.side_effect = RuntimeError('boom')
    fn(event('Update', physical_id='existing'), None)
    assert sent == [('FAILED', 'existing')]
