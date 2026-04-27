variable "environment" {
  type = string
}

variable "certificate_arn" {
  type        = string
  description = "ACM certificate ARN for the HTTPS ALB listener"
}

variable "alerting_tool_cidrs" {
  type        = list(string)
  description = "CIDR blocks for alerting tool source IPs allowed to POST /analyse without Cognito auth"
}
