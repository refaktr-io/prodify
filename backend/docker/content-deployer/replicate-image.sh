#!/bin/bash
# Make the content-deployer image available in additional regions so generated
# stacks can be created there. Creates the repository (with the cross-account
# pull policy) in each region and configures registry replication from the
# source region. Replication applies to images pushed AFTER this runs, so run
# it before build-and-push.sh.
#
# Usage: AWS_PROFILE=<profile> ./replicate-image.sh region1 region2 ...
set -euo pipefail

SOURCE_REGION="${AWS_REGION:-us-east-1}"
AWS_PROFILE="${AWS_PROFILE:-default}"
ECR_REPO_NAME="${ECR_REPO_NAME:-prodify-content-deployer}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ "$#" -eq 0 ]; then
  echo "usage: $0 <destination-region> [...]" >&2
  exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --profile "$AWS_PROFILE" --region "$SOURCE_REGION")

DESTINATIONS=""
for region in "$@"; do
  [ "$region" = "$SOURCE_REGION" ] && continue
  echo "Preparing $ECR_REPO_NAME in $region"
  aws ecr describe-repositories --repository-names "$ECR_REPO_NAME" --profile "$AWS_PROFILE" --region "$region" >/dev/null 2>&1 || \
    aws ecr create-repository --repository-name "$ECR_REPO_NAME" --image-scanning-configuration scanOnPush=true --profile "$AWS_PROFILE" --region "$region" >/dev/null
  aws ecr set-repository-policy --repository-name "$ECR_REPO_NAME" --policy-text "file://${SCRIPT_DIR}/ecr-repository-policy.json" --profile "$AWS_PROFILE" --region "$region" >/dev/null
  aws ecr put-lifecycle-policy --repository-name "$ECR_REPO_NAME" --lifecycle-policy-text "file://${SCRIPT_DIR}/ecr-lifecycle-policy.json" --profile "$AWS_PROFILE" --region "$region" >/dev/null
  DESTINATIONS="${DESTINATIONS}{\"region\":\"${region}\",\"registryId\":\"${ACCOUNT_ID}\"},"
done

DESTINATIONS="${DESTINATIONS%,}"
aws ecr put-replication-configuration --profile "$AWS_PROFILE" --region "$SOURCE_REGION" --replication-configuration \
  "{\"rules\":[{\"destinations\":[${DESTINATIONS}],\"repositoryFilters\":[{\"filter\":\"${ECR_REPO_NAME}\",\"filterType\":\"PREFIX_MATCH\"}]}]}" >/dev/null

echo
echo "Replication configured from $SOURCE_REGION to: $*"
echo "Now run build-and-push.sh, then set DeployerImageRegions to: ${SOURCE_REGION},$(IFS=,; echo "$*")"
