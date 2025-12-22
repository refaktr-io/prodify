# Prodify Landing Page

This is the landing page for Prodify, a tool to help migrate Lovable.dev apps to AWS.

## How to use

1. Open `index.html` in your web browser.
2. The page uses Tailwind CSS via CDN, so you need an internet connection.

## Features

- **Free Tier**: Drag & drop a .zip file to "generate" a CloudFormation template (simulated).
- **Paid Tier**: Information about consulting services for more complex AWS setups.

## Deployment

To deploy this landing page to AWS:
1. Create an S3 bucket.
2. Upload `index.html`.
3. Enable Static Website Hosting on the bucket.
4. (Optional) Set up CloudFront for HTTPS and custom domain.
