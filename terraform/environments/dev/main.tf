terraform {
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = ">= 2.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
  assume_role {
    role_arn     = "arn:aws:iam::${var.aws_account_id}:role/cognis-terraform-role"
    session_name = "TerraformProvisioningSession"
  }

  default_tags {
    tags = {
      Project     = "cognis"
      Environment = "dev"
      ManagedBy   = "terraform"
    }
  }
}

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

locals {
  environment     = "dev"
  frontend_domain = "dev.cognis.internal"

  vector_index_arn = "arn:aws:s3vectors:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:bucket/${module.storage.vector_bucket_name}/index/${module.storage.vector_index_name}"
}

module "networking" {
  source = "../../modules/networking"

  environment     = local.environment
  certificate_arn = var.certificate_arn
}

module "storage" {
  source = "../../modules/storage"

  environment                   = local.environment
  enable_point_in_time_recovery = false
}

module "messaging" {
  source = "../../modules/messaging"

  environment              = local.environment
  private_subnet_ids       = module.networking.private_subnet_ids
  lambda_security_group_id = module.networking.lambda_security_group_id
  incidents_table_arn      = module.storage.incidents_table_arn
  corpus_chunks_table_arn  = module.storage.corpus_chunks_table_arn
  vector_index_arn         = local.vector_index_arn
}

module "ai" {
  source = "../../modules/ai"

  environment = local.environment
}

module "observability" {
  source = "../../modules/observability"

  environment                 = local.environment
  log_retention_days          = 7
  enable_alarm_actions        = false
  xray_fixed_rate             = 1.0
  oncall_email                = var.oncall_email
  alb_arn                     = module.networking.alb_arn
  alb_target_group_arn        = module.networking.alb_target_group_arn
  ecs_cluster_name            = module.compute.ecs_cluster_name
  ecs_service_name            = module.compute.ecs_service_name
  notification_queue_name     = module.messaging.notification_queue_name
  ingestion_queue_name        = module.messaging.ingestion_queue_name
  notify_lambda_function_name = module.messaging.notify_lambda_function_name
  ingest_lambda_function_name = module.messaging.ingest_lambda_function_name
}

module "secrets" {
  source = "../../modules/secrets"

  environment                   = local.environment
  frontend_domain               = local.frontend_domain
  notification_queue_url        = module.messaging.notification_queue_url
  ingestion_queue_url           = module.messaging.ingestion_queue_url
  vector_bucket_name            = module.storage.vector_bucket_name
  vector_index_name             = module.storage.vector_index_name
  ses_recipient_addresses       = var.ses_recipient_addresses
  active_notification_providers = var.active_notification_providers
}

module "auth" {
  source = "../../modules/auth"

  environment          = local.environment
  frontend_domain      = local.frontend_domain
  alb_listener_arn     = module.networking.alb_listener_arn
  alb_target_group_arn = module.networking.alb_target_group_arn
  deletion_protection  = false
}

module "compute" {
  source = "../../modules/compute"

  environment                 = local.environment
  vpc_id                      = module.networking.vpc_id
  private_subnet_ids          = module.networking.private_subnet_ids
  ecs_security_group_id       = module.networking.ecs_security_group_id
  alb_target_group_arn        = module.networking.alb_target_group_arn
  fastapi_log_group_name      = module.observability.fastapi_log_group_name
  incidents_table_arn         = module.storage.incidents_table_arn
  chat_messages_table_arn     = module.storage.chat_messages_table_arn
  corpus_chunks_table_arn     = module.storage.corpus_chunks_table_arn
  counters_table_arn          = module.storage.counters_table_arn
  vector_index_arn            = local.vector_index_arn
  notification_queue_arn      = module.messaging.notification_queue_arn
  ingestion_queue_arn         = module.messaging.ingestion_queue_arn
  langfuse_secret_arn         = module.secrets.langfuse_secret_arn
  parameter_store_path_prefix = module.secrets.parameter_store_path_prefix
  bedrock_invoke_policy_arn   = module.ai.bedrock_invoke_policy_arn
  cpu                         = 512
  memory                      = 1024
  min_capacity                = 1
  max_capacity                = 1
  enable_autoscaling          = false
}

