terraform {
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

resource "aws_iam_openid_connect_provider" "github_actions" {
  url = "https://token.actions.githubusercontent.com"

  client_id_list = [
    "sts.amazonaws.com"
  ]

  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1"
  ]
}

resource "aws_iam_role" "github_actions_role" {
  name = "cognis-github-actions-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRoleWithWebIdentity"
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.github_actions.arn
        }
        Condition = {
          StringLike = {
            "token.actions.githubusercontent.com:sub" : "repo:jamalishaq/cognis:*"
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "github_actions_permissions" {
  name = "cognis-github-actions-policy"
  role = aws_iam_role.github_actions_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # ECR: Authenticate and Push images
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload"
        ]
        Resource = "*"
      },
      # ECS: Update and Describe services
      {
        Effect = "Allow"
        Action = [
          "ecs:UpdateService",
          "ecs:DescribeServices"
        ]
        Resource = "*"
      },
      # S3: Sync frontend build
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = "*"
      },
      # S3: Terraform state backend
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::cognis-terraform-state",
          "arn:aws:s3:::cognis-terraform-state/*"
        ]
      },
      # STS: Assume terraform execution role
      {
        Effect   = "Allow"
        Action   = "sts:AssumeRole"
        Resource = aws_iam_role.terraform_execution_role.arn
      }
    ]
  })
}

resource "aws_iam_role" "terraform_execution_role" {
  name = "cognis-terraform-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # 1. Allow Jamal (Specific User)
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:user/jamal"
        }
      },
      # 2. Allow GitHub Actions (OIDC)
      {
        Action = "sts:AssumeRoleWithWebIdentity"
        Effect = "Allow"
        Principal = {
          Federated = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/token.actions.githubusercontent.com"
        }
        Condition = {
          StringLike = {
            "token.actions.githubusercontent.com:sub" : "repo:jamalishaq/cognis:*"
          }
        }
      },
      # 3. Allow cognis-github-actions-role to assume this role
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.github_actions_role.arn
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "terraform_full_service_permissions" {
  name = "cognis-terraform-policy"
  role = aws_iam_role.terraform_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:*",
          "ecs:*",
          "ecr:*",
          "elasticloadbalancing:*",
          "lambda:*",
          "dynamodb:*",
          "s3:*",
          "s3vectors:*",
          "sqs:*",
          "iam:*",
          "cognito-idp:*",
          "secretsmanager:*",
          "ssm:*",
          "bedrock:*",
          "cloudwatch:*",
          "logs:*",
          "xray:*",
          "acm:ImportCertificate",
          "acm:DescribeCertificate",
          "acm:ListCertificates",
          "acm:DeleteCertificate",
          "acm:AddTagsToCertificate",
          "acm:ListTagsForCertificate"
        ]
        Resource = "*"
      }
    ]
  })
}

# 1. Create the 'Key' (Policy)
resource "aws_iam_policy" "allow_assume_terraform_role" {
  name        = "AllowAssumeTerraformRole"
  description = "Allows Jamal to assume the infrastructure provisioning role"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "sts:AssumeRole"
        # Reference the ARN of the role we just defined
        Resource = aws_iam_role.terraform_execution_role.arn
      }
    ]
  })
}

# 2. Create the Group
resource "aws_iam_group" "terraform_admins" {
  name = "TerraformAdmins"
}

# 3. Attach the 'Key' to the Group
resource "aws_iam_group_policy_attachment" "attach_assume_role" {
  group      = aws_iam_group.terraform_admins.name
  policy_arn = aws_iam_policy.allow_assume_terraform_role.arn
}

# 4. Put Jamal in the Group
resource "aws_iam_user_group_membership" "jamal_membership" {
  user = "jamal" # Ensure this matches the actual IAM username

  groups = [
    aws_iam_group.terraform_admins.name
  ]
}

resource "aws_s3_bucket" "terraform_state" {
  bucket = "cognis-terraform-state"

  tags = {
    Name      = "cognis-terraform-state"
    ManagedBy = "terraform"
  }
}

resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_acm_certificate" "self_signed" {
  private_key      = file("${path.root}/../../certificate/cognis_key.pem")
  certificate_body = file("${path.root}/../../certificate/cognis_cert.pem")

  tags = {
    Environment = "dev"
    Name        = "cognis-self-signed"
  }
}
