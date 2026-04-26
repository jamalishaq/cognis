# secrets/ — Resources to Provision

## Secrets Manager (sensitive values)

### Langfuse API Key
- `aws_secretsmanager_secret` langfuse — name `cognis/${var.environment}/langfuse-api-key`
- `aws_secretsmanager_secret_version` — placeholder value on create, engineer populates manually after provisioning

## Parameter Store (non-sensitive config)

All parameters use `String` type. `SecureString` is not needed — sensitive values are in Secrets Manager.

- `aws_ssm_parameter` bedrock_region — name `/cognis/${var.environment}/bedrock-region`, value `us-east-1`
- `aws_ssm_parameter` triage_model_id — name `/cognis/${var.environment}/triage-model-id`, value `anthropic.claude-haiku-4-5-20251001-v1:0`
- `aws_ssm_parameter` chat_model_id — name `/cognis/${var.environment}/chat-model-id`, value `anthropic.claude-haiku-4-5-20251001-v1:0`
- `aws_ssm_parameter` judge_model_id — name `/cognis/${var.environment}/judge-model-id`, value `anthropic.claude-haiku-4-5-20251001-v1:0`
- `aws_ssm_parameter` reasoning_model_id — name `/cognis/${var.environment}/reasoning-model-id`, value `anthropic.claude-sonnet-4-6`
- `aws_ssm_parameter` embedding_model_id — name `/cognis/${var.environment}/embedding-model-id`, value `cohere.embed-v4:0`
- `aws_ssm_parameter` rerank_model_id — name `/cognis/${var.environment}/rerank-model-id`, value `cohere.rerank-v3-5:0`
- `aws_ssm_parameter` incidents_table — name `/cognis/${var.environment}/dynamodb/incidents-table`, value `Incidents`
- `aws_ssm_parameter` chat_messages_table — name `/cognis/${var.environment}/dynamodb/chat-messages-table`, value `ChatMessages`
- `aws_ssm_parameter` corpus_chunks_table — name `/cognis/${var.environment}/dynamodb/corpus-chunks-table`, value `CorpusChunks`
- `aws_ssm_parameter` notification_queue_url — name `/cognis/${var.environment}/sqs/notification-queue-url`, value from messaging module output
- `aws_ssm_parameter` ingestion_queue_url — name `/cognis/${var.environment}/sqs/ingestion-queue-url`, value from messaging module output
- `aws_ssm_parameter` ses_sender_address — name `/cognis/${var.environment}/ses/sender-address`, value `noreply@cognis.internal`
- `aws_ssm_parameter` allowed_origins — name `/cognis/${var.environment}/cors/allowed-origins`, value `https://${var.frontend_domain}`
- `aws_ssm_parameter` frontend_domain — name `/cognis/${var.environment}/frontend-domain`, value from var.frontend_domain

## Outputs
- `langfuse_secret_arn`
- `parameter_store_path_prefix` — `/cognis/${var.environment}` (FastAPI reads all params under this prefix)
