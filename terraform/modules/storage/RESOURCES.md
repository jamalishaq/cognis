# storage/ — Resources to Provision

## S3 Buckets

### Frontend Bucket
- `aws_s3_bucket` frontend — name `cognis-${var.environment}-frontend`
- `aws_s3_bucket_versioning` — enabled
- `aws_s3_bucket_public_access_block` — public access allowed for static website hosting (ACL disabled, bucket policy controls access)
- `aws_s3_bucket_website_configuration` — index_document `index.html`, error_document `index.html` (SPA routing)
- `aws_s3_bucket_policy` — allows `s3:GetObject` from `*` (public read for static files only)
- `aws_s3_bucket_server_side_encryption_configuration` — AES256

The frontend bucket serves static HTML/CSS/JS files publicly — no sensitive data. Engineers access the React app via the S3 static website URL, which then makes API calls to the ALB.

### Terraform State Bucket (dev and prod share one bucket, different keys)
- `aws_s3_bucket` terraform_state — name `cognis-terraform-state`
- `aws_s3_bucket_versioning` — enabled (required for S3 native locking)
- `aws_s3_bucket_public_access_block` — all public access blocked
- `aws_s3_bucket_server_side_encryption_configuration` — AES256

## DynamoDB Tables

### Incidents Table
- `aws_dynamodb_table` incidents — name `Incidents`
- `billing_mode = "PAY_PER_REQUEST"` — never PROVISIONED
- Hash key: `incident_id` (String)
- Attributes: only define attributes used as keys — `incident_id` (S)
- `point_in_time_recovery` — enabled in prod

### ChatMessages Table
- `aws_dynamodb_table` chat_messages — name `ChatMessages`
- `billing_mode = "PAY_PER_REQUEST"`
- Hash key: `incident_id` (String), Range key: `message_id` (String)
- Attributes: `incident_id` (S), `message_id` (S)
- `point_in_time_recovery` — enabled in prod

### CorpusChunks Table
- `aws_dynamodb_table` corpus_chunks — name `CorpusChunks`
- `billing_mode = "PAY_PER_REQUEST"`
- Hash key: `chunk_id` (String)
- Attributes: `chunk_id` (S)
- `point_in_time_recovery` — enabled in prod

## S3 Vectors
- `aws_s3vectors_vector_bucket` — name `cognis-${var.environment}-vectors`
- `aws_s3vectors_index` — name `corpus-index`, dimensions=1024 (Cohere embed-v4), distance_metric=cosine

## Outputs
- `frontend_bucket_name`
- `frontend_bucket_arn`
- `incidents_table_name`
- `incidents_table_arn`
- `chat_messages_table_name`
- `chat_messages_table_arn`
- `corpus_chunks_table_name`
- `corpus_chunks_table_arn`
- `vector_bucket_name`
- `vector_index_name`
