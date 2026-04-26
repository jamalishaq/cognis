output "fastapi_log_group_name" {
  value = aws_cloudwatch_log_group.fastapi.name
}

output "notify_lambda_log_group_name" {
  value = aws_cloudwatch_log_group.notify_lambda.name
}

output "ingest_lambda_log_group_name" {
  value = aws_cloudwatch_log_group.ingest_lambda.name
}

output "dashboard_name" {
  value = aws_cloudwatch_dashboard.main.dashboard_name
}
