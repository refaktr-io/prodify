# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Prodify converts a Lovable.dev project export (a .zip) into a CloudFormation template that hosts the built site on S3 + CloudFront in the *user's* AWS account. This repo is the backend API and the generated-template machinery. The public website at https://refaktr.io/prodify/ is maintained in a **separate repo**; `frontend/index.html` here is the original landing page and is no longer deployed by CI.

There is no test suite, linter, or build step for the Python code. Verification is done by validating the template and running the smoke test below.

## Commands

All AWS work uses the `refaktr` CLI profile in `us-east-1`. Bucket names (`prodify-backend`, `prodify-staging`) and the stack name (`prodify-backend`) are hardcoded.

```bash
# Validate the backend template
aws cloudformation validate-template --template-body file://backend/infrastructure/template.yaml --profile refaktr --region us-east-1

# Package + deploy the backend manually (CI does the same on push to main touching backend/**)
cd backend/src && zip -r /tmp/lambda-code.zip *.py
KEY=lambda-code-$(git rev-parse --short HEAD).zip
aws s3 cp /tmp/lambda-code.zip s3://prodify-backend/$KEY --profile refaktr
cd .. && aws cloudformation deploy --template-file infrastructure/template.yaml \
  --stack-name prodify-backend --parameter-overrides LambdaCodeKey=$KEY \
  --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset --profile refaktr --region us-east-1

# Build + push the content-deployer container image (arm64) to ECR
backend/docker/content-deployer/build-and-push.sh

# Smoke test the deployed API end to end
API=https://0m1no5obe7.execute-api.us-east-1.amazonaws.com/Prod
RESP=$(curl -s -X POST $API/upload-request)
URL=$(echo "$RESP" | python3 -c 'import sys,json;print(json.load(sys.stdin)["uploadUrl"])')
RID=$(echo "$RESP" | python3 -c 'import sys,json;print(json.load(sys.stdin)["requestId"])')
curl -s -X PUT -H 'Content-Type: application/zip' --data-binary @some-project.zip "$URL"
sleep 5; curl -s $API/status/$RID      # expect {"status":"READY","templateUrl":...}
```

**The `LambdaCodeKey` must be unique per deploy.** CloudFormation only updates function code when the `Code` property changes; re-uploading to the same key silently deploys nothing. CI keys the zip by `GITHUB_SHA`. The checked-in `backend/lambda-code.zip` is a stale artifact, not what CI deploys.

## Architecture

Two AWS accounts are involved, and it matters which code runs where:

**Prodify's account** (`backend/infrastructure/template.yaml`, `backend/src/`) — a REST API (API Gateway → three Python 3.13 Lambdas) plus the `prodify-staging` S3 bucket. Everything keys off the S3 object layout, which is the contract between the functions:

- `upload_request.py` mints a `requestId` (uuid4) and a presigned PUT for `uploads/{requestId}/source.zip` (5 min).
- An S3 event notification (installed by the `S3NotificationFunction` custom resource, because CloudFormation can't declare notifications on a bucket it's also creating without a cycle) fires `generator.py` on `uploads/*.zip`.
- `generator.py` writes `generated/{requestId}/template.yaml`. The template is a Python f-string, so CloudFormation `${...}` substitutions inside it are written as `${{...}}`.
- `status.py` polls for that key and returns a **plain regional S3 URL** (`https://prodify-staging.s3.us-east-1.amazonaws.com/generated/...`). The `generated/*` prefix is anonymously readable via bucket policy — the key is unguessable and the lifecycle rule expires everything after 1 day. Do not switch this back to a presigned URL: the ~1 KB session token makes the console quick-create link overflow the AWS sign-in redirect and the link dies with the Lambda's role credentials. `uploads/*` stays private.

**The user's account** (the generated template + `backend/docker/content-deployer/`) — the template creates a private S3 bucket, a CloudFront distribution with Origin Access Control and SPA error routing, and a `Custom::ContentDeployer` resource backed by a **container-image Lambda** pulled from Prodify's ECR repo (`prodify-content-deployer`, pinned by digest in `generator.py`). `app.py` downloads the source zip via a presigned GET baked into the template (2 h), runs `bun install && bun run build` (or npm if no `bun.lockb`), and uploads `dist/` or `build/` to the site bucket. The container exists only because building a Vite project needs Node/Bun, which the managed Lambda runtimes don't provide; running the build in the user's account is deliberate so Prodify never executes untrusted `npm` scripts in its own infrastructure.

Consequences of this split worth knowing before changing things:

- A new deployer image requires bumping the `sha256` digest hardcoded in `generator.py`; `build-and-push.sh` pushes `:latest` but the template pins by digest.
- The ECR repository policy must allow **cross-account** pulls (`lambda.amazonaws.com` with `aws:sourceArn` matching any account's functions, plus caller pull permissions) or the user's stack fails at `ContentDeployer`. As of the last check the policy only allowed Prodify's own account — test generated templates from a second AWS account, not just this one.
- The presigned `SourceZipUrl` inside the generated template expires in ≤2 h, and the custom resource re-runs on every stack Update with that same URL. The Delete handler does not empty the site bucket, so generated stacks currently fail to delete while it has objects.
- Everything assumes `us-east-1` (ECR image region, quick-create link region, bucket names).

## Deployment pipeline

`.github/workflows/deploy.yml` runs on push to `main` when `backend/**` changes: zip `backend/src/*.py` → upload to `s3://prodify-backend/lambda-code-<sha>.zip` → `cloudformation deploy` with `LambdaCodeKey` overridden. It uses long-lived `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` repository secrets. It does **not** deploy the website; that happens from the website repo.
