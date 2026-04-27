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

variable "alerting_tool_cidrs" {
  type        = list(string)
  default       = ["0.0.0.0/0"]
  description = "CIDR blocks for alerting tool IPs allowed to POST /analyse (e.g. [\"YOUR_IP/32\"])"
}
