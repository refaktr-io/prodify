"""CloudFront routing in the generated site template: IndexRewriteFunction maps
extensionless paths to <path>/index.html so prerendered pages are served at
their own URLs; anything missing still falls back to the root index.html.
"""
import json
import shutil
import subprocess

import pytest
from cfnlint.decode import decode_str

from test_generator import render


@pytest.fixture(scope='module')
def resources():
    template, errors = decode_str(render())
    assert not errors
    return template['Resources']


def test_rewrite_function_runs_on_every_viewer_request(resources):
    behavior = resources['CloudFrontDistribution']['Properties']['DistributionConfig']['DefaultCacheBehavior']
    assert behavior['FunctionAssociations'] == [
        {'EventType': 'viewer-request', 'FunctionARN': {'Fn::GetAtt': ['IndexRewriteFunction', 'FunctionARN']}},
    ]


def test_missing_pages_still_fall_back_to_root_index(resources):
    errors = resources['CloudFrontDistribution']['Properties']['DistributionConfig']['CustomErrorResponses']
    assert {(e['ErrorCode'], e['ResponseCode'], e['ResponsePagePath']) for e in errors} == {
        (403, 200, '/index.html'), (404, 200, '/index.html'),
    }


@pytest.mark.skipif(shutil.which('node') is None, reason='node not installed')
@pytest.mark.parametrize('uri,expected', [
    ('/', '/index.html'),
    ('/about', '/about/index.html'),
    ('/about/', '/about/index.html'),
    ('/blog/post-1', '/blog/post-1/index.html'),
    ('/a.b/c', '/a.b/c/index.html'),
    ('/index.html', '/index.html'),
    ('/assets/app-1a2b.js', '/assets/app-1a2b.js'),
    ('/favicon.ico', '/favicon.ico'),
    ('/user/john.doe', '/user/john.doe'),
])
def test_rewrite_function(resources, uri, expected):
    code = resources['IndexRewriteFunction']['Properties']['FunctionCode']
    script = f"{code}\nprocess.stdout.write(handler({{request: {{uri: {json.dumps(uri)}}}}}).uri);"
    result = subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True)
    assert result.stdout == expected
