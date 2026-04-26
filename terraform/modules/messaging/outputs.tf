output "notification_queue_url" {
  value = aws_sqs_queue.notification.url
}

output "notification_queue_arn" {
  value = aws_sqs_queue.notification.arn
}

output "notification_queue_name" {
  value = aws_sqs_queue.notification.name
}

output "ingestion_queue_url" {
  value = aws_sqs_queue.ingestion.url
}

output "ingestion_queue_arn" {
  value = aws_sqs_queue.ingestion.arn
}

output "ingestion_queue_name" {
  value = aws_sqs_queue.ingestion.name
}

output "notification_dlq_arn" {
  value = aws_sqs_queue.notification_dlq.arn
}

output "ingestion_dlq_arn" {
  value = aws_sqs_queue.ingestion_dlq.arn
}

output "notify_lambda_arn" {
  value = aws_lambda_function.notify.arn
}

output "notify_lambda_function_name" {
  value = aws_lambda_function.notify.function_name
}

output "ingest_lambda_arn" {
  value = aws_lambda_function.ingest.arn
}

output "ingest_lambda_function_name" {
  value = aws_lambda_function.ingest.function_name
}
