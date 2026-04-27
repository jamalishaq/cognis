# messaging/ — Resources to Provision

## SQS Queues

### Notification Queue
- `aws_sqs_queue` notification — name `cognis-${var.environment}-notification`
- `visibility_timeout_seconds = 60` — must be >= Lambda timeout
- `message_retention_seconds = 86400` — 1 day
- `receive_wait_time_seconds = 20` — long polling

### Notification Dead Letter Queue
- `aws_sqs_queue` notification_dlq — name `cognis-${var.environment}-notification-dlq`
- `aws_sqs_queue_redrive_policy` on notification queue — maxReceiveCount=3, deadLetterTargetArn=DLQ ARN

### Corpus Ingestion Queue
- `aws_sqs_queue` ingestion — name `cognis-${var.environment}-ingestion`
- `visibility_timeout_seconds = 300` — ingestion Lambda runs longer than notification
- `message_retention_seconds = 86400` — 1 day
- `receive_wait_time_seconds = 20` — long polling

### Corpus Ingestion Dead Letter Queue
- `aws_sqs_queue` ingestion_dlq — name `cognis-${var.environment}-ingestion-dlq`
- `aws_sqs_queue_redrive_policy` on ingestion queue — maxReceiveCount=3, deadLetterTargetArn=DLQ ARN

## Lambda Functions

### Notification Lambda
- `aws_lambda_function` notify — function name `cognis-${var.environment}-notify`
- Runtime: python3.12
- Handler: `notify.handler`
- Source: `backend/app/notifications/notify.py` packaged as zip
- Timeout: 30 seconds
- Memory: 128 MB
- Environment variables: `SES_SENDER_ADDRESS`, `ENVIRONMENT`
- VPC config: public subnets, Lambda security group

### Notification Lambda IAM Role
- `aws_iam_role` notify_lambda — trust policy allows `lambda.amazonaws.com`
- `aws_iam_role_policy` notify_lambda_policy — inline policy:
  - `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes` on notification queue ARN only
  - `ses:SendEmail` on `*` (SES does not support resource-level ARNs)
  - `ssm:GetParameter` on Parameter Store SES path ARN
  - `logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents` for CloudWatch

### Notification Lambda SQS Trigger
- `aws_lambda_event_source_mapping` — event_source_arn=notification queue ARN, batch_size=1

### Corpus Ingestion Lambda
- `aws_lambda_function` ingest — function name `cognis-${var.environment}-ingest`
- Runtime: python3.12
- Handler: `ingest.handler`
- Source: `backend/app/notifications/ingest.py` packaged as zip
- Timeout: 300 seconds — embedding + storing can take time
- Memory: 256 MB
- Environment variables: `ENVIRONMENT`, `AWS_REGION`
- VPC config: public subnets, Lambda security group

### Corpus Ingestion Lambda IAM Role
- `aws_iam_role` ingest_lambda — trust policy allows `lambda.amazonaws.com`
- `aws_iam_role_policy` ingest_lambda_policy — inline policy:
  - `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes` on ingestion queue ARN only
  - `dynamodb:GetItem` on Incidents table ARN
  - `dynamodb:PutItem` on CorpusChunks table ARN
  - `bedrock:InvokeModel` on Cohere embed-v4 model ARN
  - `s3vectors:PutVectors` on S3 Vectors ARN
  - `logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents` for CloudWatch

### Corpus Ingestion Lambda SQS Trigger
- `aws_lambda_event_source_mapping` — event_source_arn=ingestion queue ARN, batch_size=1

## Outputs
- `notification_queue_url`
- `notification_queue_arn`
- `ingestion_queue_url`
- `ingestion_queue_arn`
- `notification_dlq_arn`
- `ingestion_dlq_arn`
- `notify_lambda_arn`
- `ingest_lambda_arn`
