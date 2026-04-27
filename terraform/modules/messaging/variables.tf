variable "environment" {
  type = string
}

variable "subnet_ids" {
  type        = list(string)
  description = "Public subnet IDs for Lambda VPC config"
}

variable "lambda_security_group_id" {
  type        = string
  description = "Security group ID for Lambda functions"
}

variable "incidents_table_arn" {
  type        = string
  description = "Incidents DynamoDB table ARN for ingest Lambda IAM policy"
}

variable "corpus_chunks_table_arn" {
  type        = string
  description = "CorpusChunks DynamoDB table ARN for ingest Lambda IAM policy"
}

variable "vector_index_arn" {
  type        = string
  description = "S3 Vectors index ARN for ingest Lambda IAM policy"
}
