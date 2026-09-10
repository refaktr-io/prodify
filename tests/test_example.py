"""examples/marios-nostalgia-bites/template.yaml must match what the current
site template renders, so the committed example never drifts from reality.

Regenerate:  STAGING_BUCKET=x python3 tests/test_example.py --write
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EXAMPLE = REPO / 'examples' / 'marios-nostalgia-bites' / 'template.yaml'

INPUTS = dict(
    source_zip_url='https://github.com/refaktr-io/marios-nostalgia-bites/archive/refs/heads/main.zip',
    account_id='532931254745',
    region_names=['us-east-1', 'us-east-2', 'us-west-2', 'ca-central-1', 'eu-west-1', 'eu-west-2', 'eu-central-1',
                  'eu-north-1', 'ap-south-1', 'ap-southeast-1', 'ap-southeast-2', 'ap-northeast-1', 'sa-east-1'],
    repository='prodify-content-deployer',
    digest='sha256:1d6d6d5e29a8f39b6a7e49ebdb615440adbf02acaced379a1f371ef762ad4886',
    generated_at='2026-09-10T04:28:42Z',
)


def render():
    import generator
    return generator.render_template(**INPUTS)


def test_example_matches_current_template():
    assert EXAMPLE.read_text() == render(), (
        'examples/marios-nostalgia-bites/template.yaml is out of date; run: STAGING_BUCKET=x python3 tests/test_example.py --write'
    )


def test_example_uses_stable_public_source_not_a_presigned_url():
    text = EXAMPLE.read_text()
    assert 'github.com/refaktr-io/marios-nostalgia-bites/archive/refs/heads/main.zip' in text
    assert 'x-amz-security-token' not in text and 'Signature=' not in text


if __name__ == '__main__':
    sys.path.insert(0, str(REPO / 'backend' / 'src'))
    if '--write' in sys.argv:
        EXAMPLE.write_text(render())
        print(f'wrote {EXAMPLE}')
    else:
        print('up to date' if EXAMPLE.read_text() == render() else 'OUT OF DATE')
