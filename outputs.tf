output "rds_endpoint" {
  value = aws_db_instance.postgres.endpoint
}

output "lambda_function_name" {
  value = aws_lambda_function.periodic_lambda.function_name
}