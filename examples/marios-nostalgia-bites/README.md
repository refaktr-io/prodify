# Sample: `marios-nostalgia-bites`

A deployable example of what Prodify generates. [`template.yaml`](template.yaml) is the CloudFormation template Prodify produces for the reference project [refaktr-io/marios-nostalgia-bites](https://github.com/refaktr-io/marios-nostalgia-bites) — an unmodified Lovable export (TanStack Start template) — with one difference: `SourceZipUrl` points at the repository's permanent GitHub archive instead of the two-hour presigned link a real upload gets, so this template keeps working.

## Deploy it (about 5 minutes)

**[Deploy the sample to AWS (us-east-1)](https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/create/review?templateURL=https%3A%2F%2Fprodify-staging.s3.us-east-1.amazonaws.com%2Fexamples%2Fmarios-nostalgia-bites%2Ftemplate.yaml&stackName=prodify-sample)**

Acknowledge that the template creates IAM resources, then **Create stack**. When it reaches `CREATE_COMPLETE`, the `SiteURL` output is the live site. Delete the stack to remove everything; the deployer empties the bucket first so deletion is clean. If the delete fails once at `CloudFrontDistribution` ("has not been disabled"), that's CloudFront propagation timing — wait a couple of minutes and delete again.

Other regions: change `region=` in the link to any of `us-east-1`, `us-east-2`, `us-west-2`, `ca-central-1`, `eu-west-1`, `eu-west-2`, `eu-central-1`, `eu-north-1`, `ap-south-1`, `ap-southeast-1`, `ap-southeast-2`, `ap-northeast-1`, `sa-east-1`. Accounts from AWS's new sign-up experience must use their assigned region (usually `us-east-2`). Brand-new accounts may need a one-time CloudFront verification first (see the main README).

Template URL, if you'd rather paste it into the console yourself:

```text
https://prodify-staging.s3.us-east-1.amazonaws.com/examples/marios-nostalgia-bites/template.yaml
```

## What the stack creates

| Resource | Purpose |
|---|---|
| `WebsiteBucket` | Private S3 bucket (Block Public Access, SSE-S3) holding the built site |
| `CloudFrontOriginAccessControl` + `WebsiteBucketPolicy` | CloudFront reads the bucket via OAC; the deployer's `.prodify/` bookkeeping is explicitly denied |
| `CloudFrontDistribution` | HTTPS redirect, HTTP/2+3, compression, managed caching/CORS/security-headers policies, 403/404 → `index.html` for SPA routing, optional custom domain via the `DomainName`/`AcmCertificateArn` parameters |
| `DeployerRole` + `ContentDeployer` | Container-image Lambda (pulled from Prodify's ECR in the stack's region via the `DeployerImage` mapping) that downloads the zip, enables TanStack Start prerendering in its build copy, builds, and syncs `.output/public/` into the bucket |
| `DeploymentTrigger` | The `Custom::ContentDeployer` resource that runs the deployer on create/update and empties the bucket on delete |

The `Rules` block rejects regions where the deployer image isn't replicated before CloudFormation evaluates anything else.

Because this sample's `SourceZipUrl` never changes, updating the stack is a no-op; to pick up new commits in the sample repo, delete and re-create the stack (or upload the repo zip through Prodify, which yields a fresh template).

## Keeping it current

This file is generated, not hand-edited. `tests/test_example.py` renders the current `backend/src/templates/site-template.yaml` with the same inputs and fails if the two differ; CI publishes it to the URL above on every deploy. Regenerate after changing the site template:

```bash
STAGING_BUCKET=x python3 tests/test_example.py --write
```
