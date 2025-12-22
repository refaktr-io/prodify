# Prodify - AWS Migration Tool

Helping AI prototype builders migrate their apps from Lovable.dev to AWS.

## Project Structure

```
prodify/
├── frontend/          # Landing page
│   └── index.html
├── backend/           # Serverless backend
│   ├── infrastructure/
│   │   └── template.yaml    # CloudFormation/SAM template
│   └── src/
│       ├── generator.py      # CFT generation Lambda
│       ├── upload_request.py # Upload URL Lambda
│       └── status.py         # Status polling Lambda
└── docs/              # Documentation
    └── README.md
```

## Features

- **Free Tier**: Drag & drop .zip file to generate CloudFormation template for S3 + CloudFront hosting
- **Paid Tier**: Consulting services for complex migrations (databases, auth, AI agents, etc.)

## Deployment

### Frontend
Host `frontend/index.html` on S3 with CloudFront or any static hosting service.

### Backend
1. Package and deploy using AWS SAM:
```bash
cd backend
sam build
sam deploy --guided
```

2. Update `frontend/index.html` with the API Gateway URL from the stack outputs.

## Cost Comparison

- Lovable.dev: $25/mo ($300/yr)
- AWS S3 + CloudFront: ~$6/yr

## License

© 2025 Prodify. All rights reserved.
