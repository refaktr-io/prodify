import os

# The handlers read their configuration at import time.
os.environ.setdefault('STAGING_BUCKET', 'test-staging-bucket')
os.environ.setdefault('AWS_DEFAULT_REGION', 'us-east-1')
os.environ.setdefault('AWS_ACCESS_KEY_ID', 'testing')
os.environ.setdefault('AWS_SECRET_ACCESS_KEY', 'testing')
os.environ.setdefault('DEPLOYER_IMAGE_REPOSITORY', 'prodify-content-deployer')
os.environ.setdefault('DEPLOYER_IMAGE_DIGEST', 'sha256:' + 'a' * 64)
os.environ.setdefault('DEPLOYER_IMAGE_REGIONS', 'us-east-1,eu-west-1')
os.environ.setdefault('MAX_UPLOAD_BYTES', str(50 * 1024 * 1024))
# Counting is a no-op without a table; usage tests patch usage.TABLE explicitly.
os.environ.setdefault('USAGE_TABLE', '')
