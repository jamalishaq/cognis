# compute/ — Resources to Provision

## ECR Repository
- `aws_ecr_repository` — name `cognis-${var.environment}`, image tag mutability MUTABLE, scan on push enabled
- `aws_ecr_lifecycle_policy` — keep last 10 tagged images, delete untagged images after 1 day

```json
{
  "rules": [
    {
      "rulePriority": 1,
      "description": "Keep last 10 images",
      "selection": {
        "tagStatus": "tagged",
        "tagPrefixList": [""],
        "countType": "imageCountMoreThan",
        "countNumber": 10
      },
      "action": { "type": "expire" }
    },
    {
      "rulePriority": 2,
      "description": "Delete untagged images after 1 day",
      "selection": {
        "tagStatus": "untagged",
        "countType": "sinceImagePushed",
        "countUnit": "days",
        "countNumber": 1
      },
      "action": { "type": "expire" }
    }
  ]
}
```

## ECS Cluster
- `aws_ecs_cluster` — name `cognis-${var.environment}`
- `aws_ecs_cluster_capacity_providers` — FARGATE and FARGATE_SPOT

## ECS Task Definition
- `aws_ecs_task_definition` — family `cognis-${var.environment}`, requires_compatibilities FARGATE, network_mode awsvpc
- CPU and memory per environment:
  - dev: cpu=512, memory=1024
  - prod: cpu=1024, memory=2048
- Container definition:
  - image: ECR repository URL with `latest` tag
  - portMappings: 8000
  - logConfiguration: awslogs driver → CloudWatch log group (from observability module)
  - secrets: fetch from Secrets Manager and Parameter Store at task start (not env vars)
  - healthCheck: command `["CMD-CMD", "curl -f http://localhost:8000/health || exit 1"]`

## ECS Task Role (IAM)
- `aws_iam_role` ecs_task_role — trust policy allows `ecs-tasks.amazonaws.com`
- `aws_iam_role_policy` ecs_task_policy — inline policy with:
  - `bedrock:InvokeModel` on triage, chat, reasoning, and embedding model ARNs
  - `bedrock:Rerank` on Cohere Rerank 3.5 ARN (via bedrock-agent-runtime client)
  - `dynamodb:GetItem`, `PutItem`, `UpdateItem`, `Query` on Incidents, ChatMessages, CorpusChunks table ARNs
  - `s3vectors:QueryVectors` on S3 Vectors ARN
  - `sqs:SendMessage` on notification queue ARN and ingestion queue ARN
  - `secretsmanager:GetSecretValue` on Langfuse secret ARN
  - `ssm:GetParameter` on Parameter Store path ARN

## ECS Task Execution Role (IAM)
- `aws_iam_role` ecs_execution_role — trust policy allows `ecs-tasks.amazonaws.com`
- Attach `AmazonECSTaskExecutionRolePolicy` managed policy
- Additional inline policy for ECR pull and CloudWatch logs

## ECS Service
- `aws_ecs_service` — launch type FARGATE, in private subnets, ECS security group
- Load balancer: target group from networking module, container name and port 8000
- Desired count: 1 (both environments — auto scaling handles prod)
- `deployment_minimum_healthy_percent = 50`, `deployment_maximum_percent = 200`
- Enable `enable_execute_command = true` for debugging

## Auto Scaling (prod only)
- `aws_appautoscaling_target` — min_capacity=1, max_capacity=3, resource_id `service/{cluster}/{service}`
- `aws_appautoscaling_policy` — target tracking, ECSServiceAverageCPUUtilization, target_value=70

## Outputs
- `ecr_repository_url`
- `ecs_cluster_name`
- `ecs_cluster_arn`
- `ecs_service_name`
- `ecs_task_role_arn`
- `ecs_execution_role_arn`
