#!/bin/bash

export TF_VAR_project_slug=$(basename "$(pwd)" | tr '-' '_')
export TF_VAR_aws_region="ca-central-1"  # Default to us-east-1 if not set
export AWS_REGION="ca-central-1"

BUCKET_NAME=$(echo ${AWS_REGION}-${TF_VAR_project_slug} | tr '_' '-')-terraform-state
TABLE_NAME=$(echo ${AWS_REGION}-${TF_VAR_project_slug} | tr '_' '-')-terraform-lock

terraform init \
  -backend-config="bucket=${BUCKET_NAME}" \
  -backend-config="dynamodb_table=${TABLE_NAME}" \
  -backend-config="region=${TF_VAR_aws_region}" \
  -backend-config="key=${TF_VAR_project_slug}.tfstate"

terraform destroy -auto-approve

cd backend

terraform init -backend=false

terraform import "aws_s3_bucket.terraform_state" "${BUCKET_NAME}" || true
terraform import "aws_dynamodb_table.terraform_state_lock" "${TABLE_NAME}" || true

aws s3 rm "s3://${BUCKET_NAME}" --recursive

terraform destroy -auto-approve

echo "Done"
