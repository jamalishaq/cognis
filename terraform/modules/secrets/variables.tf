variable "environment" {
  type = string
}

variable "frontend_domain" {
  type        = string
  description = "Frontend domain for CORS allowed origins (e.g. dev.cognis.internal)"
}

variable "notification_queue_url" {
  type        = string
  description = "Notification SQS queue URL from messaging module"
}

variable "ingestion_queue_url" {
  type        = string
  description = "Corpus ingestion SQS queue URL from messaging module"
}

variable "vector_bucket_name" {
  type        = string
  description = "S3 Vectors bucket name from storage module"
}

variable "vector_index_name" {
  type        = string
  description = "S3 Vectors index name from storage module"
}

variable "ses_recipient_addresses" {
  type        = string
  description = "Comma-separated list of SES recipient email addresses"
}

variable "active_notification_providers" {
  type        = string
  description = "Comma-separated list of active notification providers (e.g. ses,slack)"
  default     = "ses"
}
