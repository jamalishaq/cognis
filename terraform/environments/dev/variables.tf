variable "aws_account_id" {
  type        = string
  description = "AWS account ID"
}

variable "certificate_arn" {
  type        = string
  description = "ACM certificate ARN for the HTTPS ALB listener"
}

variable "oncall_email" {
  type        = string
  default     = ""
  description = "On-call engineer email for SNS alarm subscriptions (unused in dev)"
}

variable "ses_recipient_addresses" {
  type        = string
  default     = "jamaloflagos@gmail.com"
  description = "Comma-separated SES recipient email addresses"
}

variable "active_notification_providers" {
  type        = string
  default     = "ses"
  description = "Comma-separated active notification providers"
}
