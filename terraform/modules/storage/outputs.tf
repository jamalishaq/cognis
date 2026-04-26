output "frontend_bucket_name" {
  value = aws_s3_bucket.frontend.bucket
}

output "frontend_bucket_arn" {
  value = aws_s3_bucket.frontend.arn
}

output "incidents_table_name" {
  value = aws_dynamodb_table.incidents.name
}

output "incidents_table_arn" {
  value = aws_dynamodb_table.incidents.arn
}

output "chat_messages_table_name" {
  value = aws_dynamodb_table.chat_messages.name
}

output "chat_messages_table_arn" {
  value = aws_dynamodb_table.chat_messages.arn
}

output "corpus_chunks_table_name" {
  value = aws_dynamodb_table.corpus_chunks.name
}

output "corpus_chunks_table_arn" {
  value = aws_dynamodb_table.corpus_chunks.arn
}

output "counters_table_name" {
  value = aws_dynamodb_table.counters.name
}

output "counters_table_arn" {
  value = aws_dynamodb_table.counters.arn
}

output "vector_bucket_name" {
  value = aws_s3vectors_vector_bucket.main.vector_bucket_name
}

output "vector_index_name" {
  value = aws_s3vectors_index.corpus.index_name
}
