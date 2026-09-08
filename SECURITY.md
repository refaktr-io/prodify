# Security

## Reporting a vulnerability

Email **prodify@refaktr.io** with a description of the issue and steps to reproduce. You should hear back within 72 hours. Please don't open a public issue for anything that could be exploited before a fix ships.

## What runs where

Prodify has two trust boundaries, and it matters which side you're reporting about:

- **Prodify's account** runs only the intake API: it hands out presigned upload URLs, writes a CloudFormation template per upload, and serves that template. It never executes anything from the uploaded zip.
- **The user's account** runs the generated stack, including the `ContentDeployer` Lambda that downloads the zip, runs `bun`/`npm` build, and uploads the result to the site bucket. Build scripts in the uploaded project execute there, with the IAM role defined in the generated template (scoped to the site bucket and CloudWatch Logs).

## Things that are public by design

- Generated templates under `generated/<uuid>/template.yaml` in the staging bucket are anonymously readable. The key is unguessable and objects expire after one day. This is required for the AWS console quick-create link to work.
- The `prodify-content-deployer` container image is pullable by any AWS account, because Lambda in the user's account has to pull it. It is pinned by digest in every generated template.

Uploaded source zips are private and expire after one day.
