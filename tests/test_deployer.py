"""Unit tests for the content-deployer handler (no network, no Docker).

The end-to-end build path is exercised separately by tests/docker/run-local.sh.
"""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import app


def cfn_event(request_type, source_url='https://example.com/a.zip', old_source_url=None):
    event = {
        'RequestType': request_type,
        'ResponseURL': 'https://cfn.example/response',
        'StackId': 'stack', 'RequestId': 'req-1', 'LogicalResourceId': 'DeploymentTrigger',
        'ResourceProperties': {'SourceZipUrl': source_url, 'BucketName': 'site-bucket', 'DistributionId': 'E123'},
    }
    if old_source_url is not None:
        event['OldResourceProperties'] = {'SourceZipUrl': old_source_url, 'BucketName': 'site-bucket'}
    return event


def context():
    return SimpleNamespace(log_stream_name='stream', get_remaining_time_in_millis=lambda: 800_000)


@pytest.fixture
def responses():
    sent = []
    with patch.object(app, 'send_response', side_effect=lambda e, c, status, data=None, physical_id=None, reason=None:
                      sent.append({'status': status, 'data': data, 'physical_id': physical_id, 'reason': reason})):
        yield sent


def test_delete_empties_bucket_and_succeeds(responses):
    with patch.object(app, 'empty_bucket') as empty:
        app.handler(cfn_event('Delete'), context())
    empty.assert_called_once_with('site-bucket')
    assert responses[0]['status'] == 'SUCCESS'
    assert responses[0]['physical_id'] == 'prodify-content-site-bucket'


def test_update_with_same_source_is_noop(responses):
    with patch.object(app, 'read_state', return_value={'sourceZipUrl': 'https://example.com/a.zip', 'uploadedFiles': 7}), \
         patch.object(app, 'deploy') as deploy:
        app.handler(cfn_event('Update', old_source_url='https://example.com/a.zip'), context())
    deploy.assert_not_called()
    assert responses[0]['status'] == 'SUCCESS'
    assert responses[0]['data'] == {'UploadedFiles': 7}


def test_rollback_to_last_deployed_source_is_noop_even_if_url_expired(responses):
    # CloudFormation rolls back by re-sending the previous properties; the
    # previous URL is what state.json recorded, so no download is attempted.
    with patch.object(app, 'read_state', return_value={'sourceZipUrl': 'https://example.com/old.zip'}), \
         patch.object(app, 'deploy') as deploy:
        app.handler(cfn_event('Update', source_url='https://example.com/old.zip', old_source_url='https://example.com/new.zip'), context())
    deploy.assert_not_called()
    assert responses[0]['status'] == 'SUCCESS'


def test_update_with_new_source_deploys_records_state_and_invalidates(responses):
    with patch.object(app, 'read_state', return_value={'sourceZipUrl': 'https://example.com/old.zip'}), \
         patch.object(app, 'deploy', return_value=12) as deploy, \
         patch.object(app, 'write_state') as write_state, \
         patch.object(app, 'invalidate') as invalidate:
        app.handler(cfn_event('Update', source_url='https://example.com/new.zip', old_source_url='https://example.com/old.zip'), context())
    deploy.assert_called_once()
    write_state.assert_called_once_with('site-bucket', {'sourceZipUrl': 'https://example.com/new.zip', 'uploadedFiles': 12})
    invalidate.assert_called_once_with('E123', 'req-1')
    assert responses[0] == {'status': 'SUCCESS', 'data': {'UploadedFiles': 12}, 'physical_id': 'prodify-content-site-bucket', 'reason': None}


def test_create_does_not_invalidate(responses):
    with patch.object(app, 'deploy', return_value=3), patch.object(app, 'write_state'), \
         patch.object(app, 'invalidate') as invalidate:
        app.handler(cfn_event('Create'), context())
    invalidate.assert_not_called()
    assert responses[0]['status'] == 'SUCCESS'


def test_deploy_error_reports_reason(responses):
    with patch.object(app, 'deploy', side_effect=app.DeployError('The build ran out of time.')):
        app.handler(cfn_event('Create'), context())
    assert responses[0]['status'] == 'FAILED'
    assert responses[0]['reason'] == 'The build ran out of time.'


@pytest.mark.parametrize('key,expected', [
    ('index.html', 'no-cache'),
    ('about/index.html', 'no-cache'),
    ('assets/index-abc123.js', 'public, max-age=31536000, immutable'),
    ('favicon.ico', 'public, max-age=3600'),
])
def test_cache_control(key, expected):
    assert app.cache_control_for(key) == expected


@pytest.mark.parametrize('name,expected', [
    ('main.mjs', 'text/javascript'),
    ('app.js', 'text/javascript'),
    ('site.webmanifest', 'application/manifest+json'),
    ('font.woff2', 'font/woff2'),
    ('photo.jpg', 'image/jpeg'),
    ('unknown.xyz123', 'application/octet-stream'),
])
def test_content_types(name, expected):
    assert app.content_type_for(name) == expected


def test_build_env_installs_dev_dependencies():
    # NODE_ENV=production makes npm/bun skip devDependencies (vite lives there).
    assert app.BUILD_ENV.get('NODE_ENV') != 'production'
    assert app.BUILD_ENV['HOME'] == '/tmp'
    assert app.BUILD_ENV['npm_config_cache'].startswith('/tmp')


def test_find_build_output_requires_index_html_and_knows_nitro_output(tmp_path):
    (tmp_path / 'dist').mkdir()
    (tmp_path / 'dist' / 'assets.js').write_text('x')          # no index.html: not deployable
    out = tmp_path / '.output' / 'public'
    out.mkdir(parents=True)
    (out / 'index.html').write_text('<html>prerendered</html>')
    assert app.find_build_output(str(tmp_path)) == str(out)


def test_find_build_output_prefers_dist_when_it_has_index(tmp_path):
    (tmp_path / 'dist').mkdir()
    (tmp_path / 'dist' / 'index.html').write_text('x')
    assert app.find_build_output(str(tmp_path)) == str(tmp_path / 'dist')
    assert app.find_build_output(str(tmp_path / 'nowhere')) is None


def test_no_output_message_is_actionable_for_tanstack_start(tmp_path):
    (tmp_path / 'package.json').write_text(json.dumps({'dependencies': {'@tanstack/react-start': '1.0.0'}}))
    assert 'prerender' in app.no_output_message(str(tmp_path))
    (tmp_path / 'package.json').write_text(json.dumps({'dependencies': {'react': '18'}}))
    assert '.output/public' in app.no_output_message(str(tmp_path))


def test_collect_files_skips_cloudflare_routing_files(tmp_path):
    (tmp_path / 'index.html').write_text('x')
    (tmp_path / '_headers').write_text('x')
    (tmp_path / '_redirects').write_text('x')
    assert set(app.collect_files(str(tmp_path))) == {'index.html'}


def test_collect_files_skips_hidden_and_node_modules(tmp_path):
    (tmp_path / 'index.html').write_text('x')
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'assets' / 'a.js').write_text('x')
    (tmp_path / '.hidden').write_text('x')
    (tmp_path / 'node_modules').mkdir()
    (tmp_path / 'node_modules' / 'pkg.js').write_text('x')
    assert set(app.collect_files(str(tmp_path))) == {'index.html', 'assets/a.js'}
