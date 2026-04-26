variable "environment" {
  type = string
}

variable "enable_point_in_time_recovery" {
  type        = bool
  default     = false
  description = "Enable DynamoDB point-in-time recovery — true in prod"
}
