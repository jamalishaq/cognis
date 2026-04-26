# data "aws_ecr_repository" "backend_dev" {
#   name = "cognis-dev"
# }

# data "aws_ecr_repository" "backend_prod" {
#   name = "cognis-prod"
# }

# data "aws_ecs_cluster" "dev" {
#   cluster_name = "cognis-dev"
# }

# data "aws_ecs_cluster" "prod" {
#   cluster_name = "cognis-prod"
# }

# data "aws_ecs_service" "backend_dev" {
#   service_name = "cognis-dev"
#   cluster_arn  = data.aws_ecs_cluster.dev.arn
# }

# data "aws_ecs_service" "backend_prod" {
#   service_name = "cognis-prod"
#   cluster_arn  = data.aws_ecs_cluster.prod.arn
# }

# data "aws_s3_bucket" "frontend_dev" {
#   bucket = "cognis-dev-frontend"
# }

# data "aws_s3_bucket" "frontend_prod" {
#   bucket = "cognis-prod-frontend"
# }

data "aws_caller_identity" "current" {}

data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}