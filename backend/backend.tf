variable "project_slug" {
  description = "Project identifier"
  type        = string
  default     = "project_slug2123153523213"
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "eu-central-1"
}

locals {
  bucket_name = "${var.aws_region}-${replace(var.project_slug, "_", "-")}-terraform-state"
  table_name  = "${var.aws_region}-${replace(var.project_slug, "_", "-")}-terraform-lock"
}

resource "aws_s3_bucket" "terraform_state" {
  bucket = local.bucket_name

  lifecycle {
    prevent_destroy = false
  }
}

resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_dynamodb_table" "terraform_state_lock" {
  name           = local.table_name
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }
}

output "backend_config" {
  value = {
    bucket         = aws_s3_bucket.terraform_state.id
    dynamodb_table = aws_dynamodb_table.terraform_state_lock.id
    region         = var.aws_region
  }
  description = "Backend configuration values"
}
