output "langfuse_secret_arn" {
  value = aws_secretsmanager_secret.langfuse.arn
}

output "parameter_store_path_prefix" {
  value = "/cognis/${var.environment}"
}
