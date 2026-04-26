# ─── Secrets Manager ───────────────────────────────────────────────────────────

resource "aws_secretsmanager_secret" "langfuse" {
  name        = "cognis/${var.environment}/langfuse-api-key"
  description = "Langfuse API key for AI pipeline observability — populate manually after provisioning"

  tags = {
    Name        = "cognis-${var.environment}-langfuse-api-key"
    Environment = var.environment
  }
}

resource "aws_secretsmanager_secret_version" "langfuse" {
  secret_id     = aws_secretsmanager_secret.langfuse.id
  secret_string = "REPLACE_ME"

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# ─── Parameter Store ───────────────────────────────────────────────────────────

resource "aws_ssm_parameter" "bedrock_region" {
  name  = "/cognis/${var.environment}/bedrock-region"
  type  = "String"
  value = "us-east-1"

  tags = { Environment = var.environment }
}

resource "aws_ssm_parameter" "triage_model_id" {
  name  = "/cognis/${var.environment}/triage-model-id"
  type  = "String"
  value = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

  tags = { Environment = var.environment }
}

resource "aws_ssm_parameter" "chat_model_id" {
  name  = "/cognis/${var.environment}/chat-model-id"
  type  = "String"
  value = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

  tags = { Environment = var.environment }
}

resource "aws_ssm_parameter" "judge_model_id" {
  name  = "/cognis/${var.environment}/judge-model-id"
  type  = "String"
  value = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

  tags = { Environment = var.environment }
}

resource "aws_ssm_parameter" "reasoning_model_id" {
  name  = "/cognis/${var.environment}/reasoning-model-id"
  type  = "String"
  value = "us.anthropic.claude-sonnet-4-6"

  tags = { Environment = var.environment }
}

resource "aws_ssm_parameter" "embedding_model_id" {
  name  = "/cognis/${var.environment}/embedding-model-id"
  type  = "String"
  value = "us.cohere.embed-v4:0"

  tags = { Environment = var.environment }
}

resource "aws_ssm_parameter" "incidents_table" {
  name  = "/cognis/${var.environment}/dynamodb/incidents-table"
  type  = "String"
  value = "Incidents"

  tags = { Environment = var.environment }
}

resource "aws_ssm_parameter" "chat_messages_table" {
  name  = "/cognis/${var.environment}/dynamodb/chat-messages-table"
  type  = "String"
  value = "ChatMessages"

  tags = { Environment = var.environment }
}

resource "aws_ssm_parameter" "corpus_chunks_table" {
  name  = "/cognis/${var.environment}/dynamodb/corpus-chunks-table"
  type  = "String"
  value = "CorpusChunks"

  tags = { Environment = var.environment }
}

resource "aws_ssm_parameter" "notification_queue_url" {
  name  = "/cognis/${var.environment}/sqs/notification-queue-url"
  type  = "String"
  value = var.notification_queue_url

  tags = { Environment = var.environment }
}

resource "aws_ssm_parameter" "rerank_model_id" {
  name  = "/cognis/${var.environment}/rerank-model-id"
  type  = "String"
  value = "us.cohere.rerank-v3-5:0"

  tags = { Environment = var.environment }
}

resource "aws_ssm_parameter" "ingestion_queue_url" {
  name  = "/cognis/${var.environment}/sqs/ingestion-queue-url"
  type  = "String"
  value = var.ingestion_queue_url

  tags = { Environment = var.environment }
}

resource "aws_ssm_parameter" "ses_sender_address" {
  name  = "/cognis/${var.environment}/ses/sender-address"
  type  = "String"
  value = "toyinjamal@gmail.com"

  tags = { Environment = var.environment }
}

resource "aws_ssm_parameter" "allowed_origins" {
  name  = "/cognis/${var.environment}/cors/allowed-origins"
  type  = "String"
  value = "https://${var.frontend_domain}"

  tags = { Environment = var.environment }
}

resource "aws_ssm_parameter" "frontend_domain" {
  name  = "/cognis/${var.environment}/frontend-domain"
  type  = "String"
  value = var.frontend_domain

  tags = { Environment = var.environment }
}

resource "aws_ssm_parameter" "s3_vectors_bucket_name" {
  name  = "/cognis/${var.environment}/s3-vectors-bucket-name"
  type  = "String"
  value = var.vector_bucket_name

  tags = { Environment = var.environment }
}

resource "aws_ssm_parameter" "s3_vectors_index_name" {
  name  = "/cognis/${var.environment}/s3-vectors-index-name"
  type  = "String"
  value = var.vector_index_name

  tags = { Environment = var.environment }
}

resource "aws_ssm_parameter" "ses_recipient_addresses" {
  name  = "/cognis/${var.environment}/ses/recipient-addresses"
  type  = "String"
  value = var.ses_recipient_addresses

  tags = { Environment = var.environment }
}

resource "aws_ssm_parameter" "active_notification_providers" {
  name  = "/cognis/${var.environment}/active-notification-providers"
  type  = "String"
  value = var.active_notification_providers

  tags = { Environment = var.environment }
}
