# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Prodify converts a Lovable.dev project export (a .zip) into a CloudFormation template that hosts the built site on S3 + CloudFront in the *user's* AWS account. This repo is the intake API, the generated-template source, and the container image that does the deploying. The public website at https://refaktr.io/prodify/ is maintained in a **separate repo** and only calls the API.

## Commands

```bash
pip install -r requirements-dev.txt          # or: uv venv .venv && uv pip install -p .venv/bin/python -r requirements-dev.txt
pytest                                       # unit tests; includes cfn-lint of a rendered site template
pytest tests/test_deployer.py -k rollback    # single test
cfn-lint backend/infrastructure/*.yaml
AWS_PROFILE=<profile> tests/docker/run-local.sh [fixture...]   # real build path: image + Create/Update/Delete against a throwaway bucket
```

Deploying the maintainer instance (stack `prodify-backend`, account profile `refaktr`, `us-east-1`; forks substitute their own):

```bash
cd backend/src && zip -r /tmp/lambda-code.zip *.py templates/ && cd ../..
KEY=lambda-code-$(git rev-parse --short HEAD).zip
aws s3 cp /tmp/lambda-code.zip s3://prodify-backend/$KEY --profile refaktr
aws cloudformation deploy --template-file backend/infrastructure/template.yaml \
  --stack-name prodify-backend \
  --parameter-overrides LambdaCodeKey=$KEY StagingBucketName=prodify-staging AlarmEmail=prodify@refaktr.io \
  --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset --profile refaktr --region us-east-1

AWS_PROFILE=refaktr backend/docker/content-deployer/build-and-push.sh      # new deployer image; prints digest
AWS_PROFILE=refaktr backend/docker/content-deployer/replicate-image.sh <regions...>   # run BEFORE pushing when adding regions
```

Rules that bite:

- **`LambdaCodeKey` must be unique per deploy** — CloudFormation only updates function code when the `Code` property changes. CI keys it by `GITHUB_SHA`.
- **`StagingBucketName` must be passed as `prodify-staging` for the maintainer stack** (CI does this via a repository variable). Leaving it empty auto-generates a name, which would replace the live bucket.
- The Lambda zip must include `templates/`; `generator.py` reads `templates/site-template.yaml` at runtime.
- A new deployer image means a new digest: update the `DeployerImageDigest` default in `template.yaml` (that's the committed source of truth) and deploy.
- **`cloudformation deploy` keeps an existing stack's previous value for every parameter you don't pass.** Changing a template default does nothing to the live stack; CI therefore passes every parameter explicitly (it greps the digest out of the template). When deploying by hand, pass `DeployerImageDigest` too.

## Architecture

Two AWS accounts are involved, and which code runs where is the central design decision:

**Prodify's account** — `backend/infrastructure/template.yaml`, `backend/src/`. API Gateway → three Python 3.13 Lambdas + the staging bucket + alarms. The functions communicate only through the S3 key layout:

- `upload_request.py` mints a `requestId` (uuid4) and a presigned PUT for `uploads/{requestId}/source.zip` (5 min). Returns `maxUploadBytes` so clients can pre-check.
- An S3 notification (installed by the `S3NotificationFunction` custom resource, because a bucket can't declare a notification to a function that depends on the bucket) fires `generator.py` on `uploads/*.zip`.
- `generator.py` rejects oversized uploads by writing `generated/{requestId}/error.json`; otherwise renders `templates/site-template.yaml` (plain `__PLACEHOLDER__` substitution — no f-string brace escaping) into `generated/{requestId}/template.yaml`. It derives Prodify's account ID from `context.invoked_function_arn` and builds a per-region image `Mappings` block from `DEPLOYER_IMAGE_*` env vars.
- `status.py` reports `READY` (template exists), `ERROR` (error.json exists, with message), or `PENDING`. The template URL is a **plain regional S3 URL**; the `generated/*` prefix is anonymously readable via bucket policy (unguessable key, 1-day lifecycle). Do not switch this back to a presigned URL: the ~1 KB session token overflows the AWS console sign-in redirect that quick-create links pass through, and the link would die with the Lambda's role credentials. `uploads/*` stays private.

**The user's account** — the rendered `site-template.yaml` plus `backend/docker/content-deployer/`. The stack creates a private bucket, a CloudFront distribution (OAC, security headers, SPA error routing, optional `DomainName`/`AcmCertificateArn`), and a `Custom::ContentDeployer` resource backed by a container-image Lambda pulled from Prodify's ECR (`!FindInMap` on `AWS::Region`; a `Rules` assertion rejects unsupported regions up front). `app.py`:

- Create: download the presigned `SourceZipUrl` (~2 h), use `dist/`/`build/` if present, else `bun install && bun run build` (npm if no bun lockfile; never `--omit=dev` — build tools are devDependencies; caches redirected to `/tmp` because the filesystem is read-only), then sync to the bucket with `Cache-Control` (`no-cache` HTML, `immutable` `assets/*`) and delete stale keys.
- Update: no-op if `SourceZipUrl` equals the last successfully deployed URL recorded in `.prodify/state.json` in the site bucket — this is what makes CloudFormation rollbacks safe when the old URL has expired. Otherwise redeploy and invalidate `/*`.
- Delete: empty the bucket so the stack can delete it.
- Stable `PhysicalResourceId` (`prodify-content-<bucket>`), so updates don't trigger delete-old-resource churn.

The container exists only because building a Vite project needs Node/Bun. Running the build in the user's account is deliberate: Prodify never executes untrusted `npm` scripts in its own infrastructure. Consequences:

- The ECR repository policy (`ecr-repository-policy.json`) must allow pulls by any account and by `lambda.amazonaws.com` for any function ARN; `build-and-push.sh`/`replicate-image.sh` apply it. Test generated templates from an account that isn't the maintainer's.
- The image is pinned by digest in every generated template, so old templates keep working after a new push; the lifecycle rule only expires untagged images.
- Every region in `DeployerImageRegions` needs the image replicated there (`replicate-image.sh`, which must run before the push it should replicate).

## Deployment pipeline

`.github/workflows/deploy.yml` runs on push to `main` (backend template, `backend/src/**`, or the workflow): zip → `s3://$DEPLOYMENT_BUCKET/lambda-code-<sha>.zip` → `cloudformation deploy` with parameters from repository variables (`AWS_DEPLOY_ROLE_ARN`, `STAGING_BUCKET_NAME`, `ALARM_EMAIL`, `DEPLOYER_IMAGE_REGIONS`, ...). Auth is a GitHub OIDC role from `backend/infrastructure/github-oidc.yaml` (deployed once, manually). `validate.yml` runs cfn-lint and pytest on pull requests. Neither workflow deploys the website.

The API Gateway `Deployment` resource is immutable: rename its logical ID when adding or changing methods, or the `Prod` stage keeps serving the old deployment.

## AWS Agent Toolkit

This repo enables the `aws-core` plugin from the [Agent Toolkit for AWS](https://github.com/aws/agent-toolkit-for-aws) via `.claude/settings.json` (AWS skills + the AWS MCP Server). The marketplace registers automatically when the folder is trusted; the plugin itself needs a one-time install per developer: `claude plugin install aws-core@agent-toolkit-for-aws`. AWS credentials are per-developer — see the README's "Working with AI coding agents" section.

<!-- BEGIN AWS Agent Toolkit rules -->
# AWS Guidance

- Where these AWS rules conflict with the project's own instructions, the
  project's instructions take precedence.
- Prefer the AWS MCP Server for AWS interactions — it provides sandboxed
  execution, observability, and audit logging. If unavailable, use the
  AWS CLI directly.
- Before starting a task, check whether a relevant AWS skill is available.
  Load the skill with `retrieve_skill` and prefer its guidance over
  general knowledge.
- When uncertain about specific AWS details (API parameters, permissions,
  limits, error codes), verify against documentation rather than guessing.
  State uncertainty explicitly if you cannot confirm.
- When creating infrastructure, prefer infrastructure-as-code (AWS CDK or
  CloudFormation) over direct CLI commands.
- When working with infrastructure, follow AWS Well-Architected Framework
  principles.
- Do not use em dashes in AWS resource names or descriptions. Use
  hyphens instead.

## Secret Safety

- MUST load the `aws-secrets-manager` skill first for any secret,
  credential, API key, token, or password task. MUST NOT call
  `secretsmanager get-secret-value` or `batch-get-secret-value`, and MUST
  NOT hit the Secrets Manager Agent daemon directly. MUST use
  `{{resolve:secretsmanager:secret-id:SecretString:json-key}}` with
  `asm-exec` so the secret resolves at runtime without entering context.
<!-- END AWS Agent Toolkit rules -->
