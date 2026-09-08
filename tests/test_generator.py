import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import generator

DIGEST = 'sha256:' + 'a' * 64
REGIONS = ['us-east-1', 'eu-west-1']


def render():
    return generator.render_template(
        'https://bucket.s3.amazonaws.com/uploads/abc/source.zip?X-Amz-Signature=sig',
        '123456789012', REGIONS, 'prodify-content-deployer', DIGEST, '2026-01-01T00:00:00Z',
    )


def test_render_substitutes_every_placeholder():
    out = render()
    assert '__' not in out.replace('__MACOSX', '')
    assert 'SourceZipUrl: "https://bucket.s3.amazonaws.com/uploads/abc/source.zip?X-Amz-Signature=sig"' in out
    assert f'123456789012.dkr.ecr.eu-west-1.amazonaws.com/prodify-content-deployer@{DIGEST}' in out
    assert json.dumps(REGIONS) in out


def test_rendered_template_passes_cfn_lint():
    from cfnlint.api import ManualArgs, lint

    # Lint for the regions the template declares support for (its Rules block
    # rejects any other region before CloudFormation evaluates resources).
    matches = lint(render(), config=ManualArgs(regions=REGIONS))
    assert not matches, '\n'.join(str(m) for m in matches)


def s3_event(key, size):
    return {'Records': [{'s3': {'object': {'key': key, 'size': size}}}]}


def lambda_context():
    return SimpleNamespace(invoked_function_arn='arn:aws:lambda:us-east-1:123456789012:function:prodify-generator')


def test_handler_writes_template_for_valid_upload():
    with patch.object(generator, 's3') as s3:
        s3.generate_presigned_url.return_value = 'https://signed.example/source.zip'
        generator.handler(s3_event('uploads/req-1/source.zip', 1024), lambda_context())

    s3.put_object.assert_called_once()
    kwargs = s3.put_object.call_args.kwargs
    assert kwargs['Key'] == 'generated/req-1/template.yaml'
    assert 'https://signed.example/source.zip' in kwargs['Body']
    assert '123456789012.dkr.ecr.us-east-1.amazonaws.com' in kwargs['Body']
    s3.delete_object.assert_not_called()


def test_handler_rejects_oversized_upload_with_error_marker():
    with patch.object(generator, 's3') as s3:
        generator.handler(s3_event('uploads/req-2/source.zip', 200 * 1024 * 1024), lambda_context())

    s3.delete_object.assert_called_once_with(Bucket=generator.BUCKET_NAME, Key='uploads/req-2/source.zip')
    kwargs = s3.put_object.call_args.kwargs
    assert kwargs['Key'] == 'generated/req-2/error.json'
    assert json.loads(kwargs['Body'])['status'] == 'ERROR'
    s3.generate_presigned_url.assert_not_called()


@pytest.mark.parametrize('key', ['uploads/source.zip', 'other/req/source.zip', 'uploads/req/notes.zip'])
def test_handler_ignores_unexpected_keys(key):
    with patch.object(generator, 's3') as s3:
        generator.handler(s3_event(key, 10), lambda_context())
    s3.put_object.assert_not_called()
