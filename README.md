# Prodify

Migrate Lovable.dev apps to AWS. Stop paying $300/yr for hosting. Deploy to S3 + CloudFront for ~$6/yr.

## Features

**Free Tier:** Upload a .zip of your Lovable project → Get a one-click CloudFormation template that deploys to S3 + CloudFront

**Paid Tier:** Custom consulting for complex migrations (databases, auth, AI agents, backends)

## Architecture

```
prodify/
├── frontend/              # Landing page
│   └── index.html
├── backend/
│   ├── infrastructure/
│   │   └── template.yaml  # CloudFormation template
│   └── src/               # Lambda functions
│       ├── upload_request.py
│       ├── status.py
│       └── generator.py
└── .github/workflows/     # CI/CD
    └── deploy.yml
```

### How It Works

1. User uploads .zip → Gets presigned S3 upload URL
2. File uploads to S3 → Triggers Generator Lambda
3. Generator creates CloudFormation template with embedded content deployer
4. User gets "Deploy to AWS" button → Opens AWS Console with pre-loaded stack

## Deployment

### Prerequisites
- AWS Account
- GitHub repository secrets:
  - `AWS_ACCESS_KEY_ID`
  - `AWS_SECRET_ACCESS_KEY`

### Deploy Backend
Push to `main` branch triggers GitHub Actions to:
1. Package Lambda code → Upload to S3
2. Deploy CloudFormation stack
3. Update frontend with API URL

Or deploy manually:
```bash
cd backend/src
zip -r ../lambda-code.zip *.py
aws s3 cp ../lambda-code.zip s3://prodify-deploy-<ACCOUNT_ID>-us-east-1/

cd ..
aws cloudformation deploy \
  --template-file infrastructure/template.yaml \
  --stack-name prodify-backend \
  --capabilities CAPABILITY_IAM \
  --profile refaktr
```

### Deploy Frontend
Upload `frontend/index.html` to S3 with static hosting enabled.

## Cost Analysis

| Service | Lovable | AWS (Prodify) |
|---------|---------|---------------|
| Hosting | $300/yr | ~$6/yr |

**AWS Breakdown:**
- API Gateway: Free tier (1M requests/month)
- Lambda: Free tier (1M requests/month)  
- S3: ~$0.023/GB/month
- CloudFront: Pay per use

## License

© 2025 Prodify. All rights reserved.

