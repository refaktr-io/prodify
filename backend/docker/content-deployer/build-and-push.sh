#!/bin/bash
set -e

# Configuration
AWS_REGION="us-east-1"
AWS_PROFILE="refaktr"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --profile $AWS_PROFILE --region $AWS_REGION)
ECR_REPO_NAME="prodify-content-deployer"
IMAGE_TAG="latest"
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}"

echo "Building and pushing Content Deployer Lambda container..."
echo "AWS Account: $ACCOUNT_ID"
echo "ECR Repository: $ECR_URI"

# Create ECR repository if it doesn't exist
aws ecr describe-repositories --repository-names $ECR_REPO_NAME --profile $AWS_PROFILE --region $AWS_REGION 2>/dev/null || \
    aws ecr create-repository --repository-name $ECR_REPO_NAME --profile $AWS_PROFILE --region $AWS_REGION

# Login to ECR
aws ecr get-login-password --profile $AWS_PROFILE --region $AWS_REGION | \
    docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

# Build the Docker image for ARM64 (Lambda Graviton2)
cd "$(dirname "$0")"
docker buildx build --platform linux/arm64 -t ${ECR_REPO_NAME}:${IMAGE_TAG} --load .

# Tag the image
docker tag ${ECR_REPO_NAME}:${IMAGE_TAG} ${ECR_URI}:${IMAGE_TAG}

# Push to ECR
docker push ${ECR_URI}:${IMAGE_TAG}

echo ""
echo "✅ Successfully pushed image to ECR"
echo "Image URI: ${ECR_URI}:${IMAGE_TAG}"
echo ""
echo "Update your CloudFormation template to use this image URI in the ContentDeployer Lambda function."
