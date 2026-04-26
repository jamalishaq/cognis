variable "environment" {
  type = string
}

variable "frontend_domain" {
  type        = string
  description = "Frontend domain for Cognito callback and logout URLs (e.g. dev.cognis.internal)"
}

variable "alb_listener_arn" {
  type        = string
  description = "ALB HTTPS listener ARN to attach the Cognito auth rule to"
}

variable "alb_target_group_arn" {
  type        = string
  description = "ALB target group ARN to forward authenticated requests to"
}

variable "deletion_protection" {
  type        = bool
  default     = false
  description = "Enable Cognito User Pool deletion protection — true in prod"
}
