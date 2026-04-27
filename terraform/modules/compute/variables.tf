variable "environment" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type        = list(string)
  description = "Public subnet IDs for ECS Fargate tasks"
}

variable "ecs_security_group_id" {
  type        = string
  description = "Security group ID for ECS tasks"
}

variable "alb_target_group_arn" {
  type        = string
  description = "ALB target group ARN to register ECS tasks with"
}

variable "fastapi_log_group_name" {
  type        = string
  description = "CloudWatch log group name for FastAPI container logs"
}

variable "incidents_table_arn" {
  type = string
}

variable "chat_messages_table_arn" {
  type = string
}

variable "corpus_chunks_table_arn" {
  type = string
}

variable "vector_index_arn" {
  type        = string
  description = "S3 Vectors index ARN for QueryVectors IAM permission"
}

variable "notification_queue_arn" {
  type = string
}

variable "ingestion_queue_arn" {
  type = string
}

variable "langfuse_secret_arn" {
  type        = string
  description = "Secrets Manager ARN for Langfuse API key"
}

variable "parameter_store_path_prefix" {
  type        = string
  description = "SSM Parameter Store path prefix (e.g. /cognis/dev)"
}

variable "bedrock_invoke_policy_arn" {
  type        = string
  description = "IAM policy ARN from the ai/ module to attach to the ECS task role"
}

variable "cpu" {
  type        = number
  description = "ECS task CPU units — 512 for dev, 1024 for prod"
}

variable "memory" {
  type        = number
  description = "ECS task memory in MiB — 1024 for dev, 2048 for prod"
}

variable "min_capacity" {
  type        = number
  default     = 1
  description = "Minimum ECS task count for auto scaling"
}

variable "max_capacity" {
  type        = number
  default     = 1
  description = "Maximum ECS task count for auto scaling"
}

variable "enable_autoscaling" {
  type        = bool
  default     = false
  description = "Enable ECS auto scaling — true in prod only"
}
