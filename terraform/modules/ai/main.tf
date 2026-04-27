data "aws_caller_identity" "current" {}

resource "aws_iam_policy" "bedrock_invoke" {
  name        = "cognis-${var.environment}-bedrock-invoke"
  description = "Allows Bedrock model invocation and reranking for Cognis"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = [
          "arn:aws:bedrock:*::foundation-model/us.anthropic.claude-haiku-4-5-20251001-v1:0",
          "arn:aws:bedrock:*::foundation-model/us.anthropic.claude-sonnet-4-6",
          "arn:aws:bedrock:*::foundation-model/cohere.embed-v4:0",
          "arn:aws:bedrock:*::foundation-model/cohere.embed-english-v4:0",
          "arn:aws:bedrock:*::foundation-model/us.cohere.embed-v4:0",
          "arn:aws:bedrock:*::foundation-model/amazon.nova-micro-v1:0",
          "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:inference-profile/us.cohere.embed-v4:0",
          "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:inference-profile/us.cohere.embed-english-v4:0",
          "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0",
          "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:inference-profile/us.anthropic.claude-sonnet-4-6",
          "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:inference-profile/amazon.nova-micro-v1:0"
        ]
      },
      {
        Effect   = "Allow"
        Action   = "bedrock:Rerank"
        Resource = "arn:aws:bedrock:*::foundation-model/us.cohere.rerank-v3-5:0"
      }
    ]
  })

  tags = {
    Name        = "cognis-${var.environment}-bedrock-invoke"
    Environment = var.environment
  }
}
