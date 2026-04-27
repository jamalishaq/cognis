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
  description = "On-call engineer email for SNS alarm subscriptions"
}

variable "ses_recipient_addresses" {
  type        = string
  description = "Comma-separated SES recipient email addresses"
}

variable "active_notification_providers" {
  type        = string
  default     = "ses"
  description = "Comma-separated active notification providers"
}

variable "alerting_tool_cidrs" {
  type        = list(string)
  description = "CIDR blocks for alerting tool IPs allowed to POST /analyse (e.g. PagerDuty, Grafana Cloud published ranges)"
}
