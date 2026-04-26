# ai/ — Resources to Provision

This module provisions IAM policies for Bedrock access. Bedrock itself is a managed AWS service — no resources to create, only IAM permissions to grant.

## Bedrock Model Access

Bedrock model access must be enabled manually in the AWS console before Terraform runs — it cannot be automated via Terraform. Enable the following models in `us-east-1`:

- `anthropic.claude-haiku-4-5-20251001-v1:0` (triage + chat + judge)
- `anthropic.claude-sonnet-4-6` (reasoning agent)
- `cohere.embed-v4:0` (embeddings — set dimensions=1024)
- `cohere.rerank-v3-5:0` (reranking — only rerank model supported in us-east-1)

## IAM Policy — Bedrock Model Invocation + Reranking

- `aws_iam_policy` bedrock_invoke — name `cognis-${var.environment}-bedrock-invoke`
- Allows `bedrock:InvokeModel` on specific model ARNs:
- Allows `bedrock:Rerank` on Cohere Rerank 3.5 ARN (called via bedrock-agent-runtime client)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "bedrock:InvokeModel",
      "Resource": [
        "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
        "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-4-6",
        "arn:aws:bedrock:us-east-1::foundation-model/cohere.embed-v4:0"
      ]
    },
    {
      "Effect": "Allow",
      "Action": "bedrock:Rerank",
      "Resource": "arn:aws:bedrock:us-east-1::foundation-model/cohere.rerank-v3-5:0"
    }
  ]
}
```

This policy is attached to:
- ECS task role (triage, chat, reasoning agent, embedding, reranking calls)
- Corpus ingestion Lambda role (embedding calls only — no reranking needed during ingestion)

**Note:** Reranking uses the `bedrock-agent-runtime` boto3 client, not `bedrock-runtime`. Both clients must be initialised in `services/bedrock.py`.

## Outputs
- `bedrock_invoke_policy_arn` — attached to ECS task role and ingestion Lambda role in their respective modules
