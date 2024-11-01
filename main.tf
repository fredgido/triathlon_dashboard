terraform {
  backend "s3" {
    bucket         = "${var.aws_region}-${replace(var.project_slug, "_", "-")}-terraform-state"
    key            = "main/terraform.tfstate"
    region         = var.aws_region
    dynamodb_table = "${var.aws_region}-${replace(var.project_slug, "_", "-")}-terraform-lock"
    encrypt        = false
  }
}

variable "project_slug" {
  description = "The project identifier"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "eu-central-1"
}

provider "aws" {
  region = var.aws_region
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "random_password" "password" {
  length           = 16
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "aws_secretsmanager_secret" "db_credentials" {
  name                           = "${var.project_slug}_${var.aws_region}_secrets"
  force_overwrite_replica_secret = true
  recovery_window_in_days        = 0
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    username = "${var.project_slug}_user"
    password = random_password.password.result
    host     = aws_db_instance.postgres.endpoint
    dbname   = "${var.project_slug}_db"
  })
  depends_on = [aws_db_instance.postgres]
}

resource "aws_security_group" "rds" {
  name        = "${var.project_slug}_${var.aws_region}_postgres_rds_security_group"
  description = "RDS Security group"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # WARNING its open to all for db review
  }
}

resource "aws_db_instance" "postgres" {
  identifier          = "${replace(var.project_slug, "_", "-")}-db"
  engine              = "postgres"
  engine_version      = "16.4"
  instance_class      = "db.t3.micro"
  storage_type        = "gp3"
  allocated_storage   = 20
  publicly_accessible = true

  db_name  = "${var.project_slug}_db"
  username = "${var.project_slug}_user"
  password = random_password.password.result

  vpc_security_group_ids = [aws_security_group.rds.id]
  skip_final_snapshot    = true
  depends_on = [
    aws_security_group.rds
  ]
}

resource "aws_s3_bucket" "lambda_bucket" {
  bucket = "${replace(var.project_slug, "_", "-")}-lambda-deployments-${var.aws_region}"
}

resource "aws_s3_bucket_versioning" "lambda_bucket_versioning" {
  bucket = aws_s3_bucket.lambda_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

# generated zips were too large for a POST in the API
resource "aws_s3_object" "lambda_package" {
  bucket      = aws_s3_bucket.lambda_bucket.id
  key         = "${var.project_slug}_lambda.zip"
  source      = "${var.project_slug}_lambda.zip"
  source_hash = filebase64sha256("${var.project_slug}_lambda.zip")
}

resource "aws_iam_role" "lambda_role" {
  name = "${var.project_slug}_${var.aws_region}_iam_lambda_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "lambda_policy" {
  name = "${var.project_slug}_${var.aws_region}_lambda_runner_policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "cloudwatch:PutMetricData",
          "secretsmanager:GetSecretValue",
          "s3:GetObject"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_lambda_function" "periodic_lambda" {
  function_name    = "${var.project_slug}_${var.aws_region}_periodic_task"
  s3_bucket        = aws_s3_bucket.lambda_bucket.id
  s3_key           = aws_s3_object.lambda_package.key
  source_code_hash = aws_s3_object.lambda_package.source_hash

  role    = aws_iam_role.lambda_role.arn
  handler = "lambda_function.lambda_handler"
  runtime = "python3.12"
  timeout = 120

  environment {
    variables = {
      SECRET_NAME = aws_secretsmanager_secret.db_credentials.name
    }
  }
  depends_on = [
    aws_iam_role.lambda_role,
    aws_iam_role_policy.lambda_policy,
    aws_s3_object.lambda_package
  ]
}

resource "aws_cloudwatch_event_rule" "periodic_trigger" {
  name                = "${var.project_slug}_periodic_lambda_trigger"
  description         = "Hourly trigger"
  schedule_expression = "cron(0 * * * ? *)"
}

resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.periodic_trigger.name
  target_id = "PeriodicLambdaFunction"
  arn       = aws_lambda_function.periodic_lambda.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.periodic_lambda.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.periodic_trigger.arn
}