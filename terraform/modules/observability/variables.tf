variable "environment" {
  type = string
}

variable "log_retention_days" {
  type        = number
  description = "CloudWatch log retention in days — 7 for dev, 30 for prod"
}

variable "enable_alarm_actions" {
  type        = bool
  description = "Enable CloudWatch alarm actions — false in dev, true in prod"
}

variable "alb_arn" {
  type        = string
  description = "ALB ARN for CloudWatch metric dimensions"
}

variable "alb_target_group_arn" {
  type        = string
  description = "ALB target group ARN for CloudWatch metric dimensions"
}

variable "ecs_cluster_name" {
  type        = string
  description = "ECS cluster name for CloudWatch metric dimensions"
}

variable "ecs_service_name" {
  type        = string
  description = "ECS service name for CloudWatch metric dimensions"
}

variable "notification_queue_name" {
  type        = string
  description = "Notification SQS queue name for CloudWatch metric dimensions"
}

variable "ingestion_queue_name" {
  type        = string
  description = "Ingestion SQS queue name for CloudWatch metric dimensions"
}

variable "notify_lambda_function_name" {
  type        = string
  description = "Notification Lambda function name for CloudWatch metric dimensions"
}

variable "ingest_lambda_function_name" {
  type        = string
  description = "Ingestion Lambda function name for CloudWatch metric dimensions"
}

variable "xray_fixed_rate" {
  type        = number
  description = "X-Ray sampling rate — 1.0 for dev (all), 0.1 for prod (10%)"
}

variable "oncall_email" {
  type        = string
  default     = ""
  description = "On-call engineer email for SNS alarm subscription (prod only)"
}
