#!/bin/bash
# Build the content-deployer image for arm64, push it to ECR, apply the
# repository/lifecycle policies, and print the digest to pin in the
# backend stack's DeployerImageUri parameter.
#
# Usage: AWS_PROFILE=<profile> AWS_REGION=<region> ./build-and-push.sh [tag]
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_PROFILE="${AWS_PROFILE:-default}"
ECR_REPO_NAME="${ECR_REPO_NAME:-prodify-content-deployer}"
IMAGE_TAG="${1:-$(date +%Y%m%d-%H%M%S)}"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --profile "$AWS_PROFILE" --region "$AWS_REGION")
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
ECR_URI="${REGISTRY}/${ECR_REPO_NAME}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Account: $ACCOUNT_ID  Region: $AWS_REGION  Repo: $ECR_URI  Tag: $IMAGE_TAG"

aws ecr describe-repositories --repository-names "$ECR_REPO_NAME" --profile "$AWS_PROFILE" --region "$AWS_REGION" >/dev/null 2>&1 || \
    aws ecr create-repository --repository-name "$ECR_REPO_NAME" --image-scanning-configuration scanOnPush=true --profile "$AWS_PROFILE" --region "$AWS_REGION" >/dev/null

# Generated templates run in other accounts, so Lambda there must be able to pull this image.
aws ecr set-repository-policy --repository-name "$ECR_REPO_NAME" --policy-text "file://${SCRIPT_DIR}/ecr-repository-policy.json" --profile "$AWS_PROFILE" --region "$AWS_REGION" >/dev/null
aws ecr put-lifecycle-policy --repository-name "$ECR_REPO_NAME" --lifecycle-policy-text "file://${SCRIPT_DIR}/ecr-lifecycle-policy.json" --profile "$AWS_PROFILE" --region "$AWS_REGION" >/dev/null

aws ecr get-login-password --profile "$AWS_PROFILE" --region "$AWS_REGION" | \
    docker login --username AWS --password-stdin "$REGISTRY"

docker buildx build --platform linux/arm64 --provenance=false -t "${ECR_URI}:${IMAGE_TAG}" --push "$SCRIPT_DIR"

DIGEST=$(aws ecr describe-images --repository-name "$ECR_REPO_NAME" --image-ids imageTag="$IMAGE_TAG" --query 'imageDetails[0].imageDigest' --output text --profile "$AWS_PROFILE" --region "$AWS_REGION")

echo
echo "Pushed ${ECR_URI}:${IMAGE_TAG}"
echo "Digest: ${DIGEST}"
echo
echo "Deploy the backend with:"
echo "  --parameter-overrides DeployerImageUri=${ECR_URI}@${DIGEST}"
