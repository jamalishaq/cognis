# ─── SQS Queues ────────────────────────────────────────────────────────────────

resource "aws_sqs_queue" "notification_dlq" {
  name                      = "cognis-${var.environment}-notification-dlq"
  message_retention_seconds = 86400

  tags = {
    Name        = "cognis-${var.environment}-notification-dlq"
    Environment = var.environment
  }
}

resource "aws_sqs_queue" "notification" {
  name                       = "cognis-${var.environment}-notification"
  visibility_timeout_seconds = 60
  message_retention_seconds  = 86400
  receive_wait_time_seconds  = 20

  tags = {
    Name        = "cognis-${var.environment}-notification"
    Environment = var.environment
  }
}

resource "aws_sqs_queue_redrive_policy" "notification" {
  queue_url = aws_sqs_queue.notification.url
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.notification_dlq.arn
    maxReceiveCount     = 3
  })
}

resource "aws_sqs_queue" "ingestion_dlq" {
  name                      = "cognis-${var.environment}-ingestion-dlq"
  message_retention_seconds = 86400

  tags = {
    Name        = "cognis-${var.environment}-ingestion-dlq"
    Environment = var.environment
  }
}

resource "aws_sqs_queue" "ingestion" {
  name                       = "cognis-${var.environment}-ingestion"
  visibility_timeout_seconds = 300
  message_retention_seconds  = 86400
  receive_wait_time_seconds  = 20

  tags = {
    Name        = "cognis-${var.environment}-ingestion"
    Environment = var.environment
  }
}

resource "aws_sqs_queue_redrive_policy" "ingestion" {
  queue_url = aws_sqs_queue.ingestion.url
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.ingestion_dlq.arn
    maxReceiveCount     = 3
  })
}

# ─── Notification Lambda ───────────────────────────────────────────────────────

resource "aws_iam_role" "notify_lambda" {
  name = "cognis-${var.environment}-notify-lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = {
    Name        = "cognis-${var.environment}-notify-lambda"
    Environment = var.environment
  }
}

resource "aws_iam_role_policy" "notify_lambda" {
  name = "cognis-${var.environment}-notify-lambda-policy"
  role = aws_iam_role.notify_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = aws_sqs_queue.notification.arn
      },
      {
        Effect   = "Allow"
        Action   = "ses:SendEmail"
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = "ssm:GetParameter"
        Resource = "arn:aws:ssm:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:parameter/cognis/${var.environment}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:log-group:/cognis/${var.environment}/lambda/notify:*"
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:CreateNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DeleteNetworkInterface"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_lambda_function" "notify" {
  function_name = "cognis-${var.environment}-notify"
  role          = aws_iam_role.notify_lambda.arn
  runtime       = "python3.12"
  handler       = "notify.handler"
  timeout       = 30
  memory_size   = 128

  filename         = data.archive_file.notify.output_path
  source_code_hash = data.archive_file.notify.output_base64sha256

  environment {
    variables = {
      SES_SENDER_ADDRESS = "noreply@cognis.internal"
      ENVIRONMENT        = var.environment
    }
  }

  vpc_config {
    subnet_ids         = var.subnet_ids
    security_group_ids = [var.lambda_security_group_id]
  }

  tags = {
    Name        = "cognis-${var.environment}-notify"
    Environment = var.environment
  }
}

resource "aws_lambda_event_source_mapping" "notify" {
  event_source_arn = aws_sqs_queue.notification.arn
  function_name    = aws_lambda_function.notify.arn
  batch_size       = 1
}

# ─── Corpus Ingestion Lambda ───────────────────────────────────────────────────

resource "aws_iam_role" "ingest_lambda" {
  name = "cognis-${var.environment}-ingest-lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = {
    Name        = "cognis-${var.environment}-ingest-lambda"
    Environment = var.environment
  }
}

resource "aws_iam_role_policy" "ingest_lambda" {
  name = "cognis-${var.environment}-ingest-lambda-policy"
  role = aws_iam_role.ingest_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = aws_sqs_queue.ingestion.arn
      },
      {
        Effect   = "Allow"
        Action   = "dynamodb:GetItem"
        Resource = var.incidents_table_arn
      },
      {
        Effect   = "Allow"
        Action   = "dynamodb:PutItem"
        Resource = var.corpus_chunks_table_arn
      },
      {
        Effect   = "Allow"
        Action   = "bedrock:InvokeModel"
        Resource = "arn:aws:bedrock:${data.aws_region.current.id}::foundation-model/cohere.embed-v4:0"
      },
      {
        Effect   = "Allow"
        Action   = "s3vectors:PutVectors"
        Resource = var.vector_index_arn
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:log-group:/cognis/${var.environment}/lambda/ingest:*"
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:CreateNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DeleteNetworkInterface"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_lambda_function" "ingest" {
  function_name = "cognis-${var.environment}-ingest"
  role          = aws_iam_role.ingest_lambda.arn
  runtime       = "python3.12"
  handler       = "ingest.handler"
  timeout       = 300
  memory_size   = 256

  filename         = data.archive_file.ingest.output_path
  source_code_hash = data.archive_file.ingest.output_base64sha256

  environment {
    variables = {
      ENVIRONMENT = var.environment
      AWS_REGION  = data.aws_region.current.id
    }
  }

  vpc_config {
    subnet_ids         = var.subnet_ids
    security_group_ids = [var.lambda_security_group_id]
  }

  tags = {
    Name        = "cognis-${var.environment}-ingest"
    Environment = var.environment
  }
}

resource "aws_lambda_event_source_mapping" "ingest" {
  event_source_arn = aws_sqs_queue.ingestion.arn
  function_name    = aws_lambda_function.ingest.arn
  batch_size       = 1
}
