# networking/ — Resources to Provision

## VPC
- `aws_vpc` — CIDR `10.0.0.0/16`, DNS hostnames enabled, DNS resolution enabled

## Subnets
- `aws_subnet` x2 public — `10.0.1.0/24` (us-east-1a), `10.0.2.0/24` (us-east-1b), `map_public_ip_on_launch = true`
- `aws_subnet` x2 private — `10.0.3.0/24` (us-east-1a), `10.0.4.0/24` (us-east-1b)

## Internet & NAT Gateway
- `aws_internet_gateway` — attached to VPC
- `aws_eip` — for NAT Gateway (one per AZ is ideal but one is sufficient for capstone)
- `aws_nat_gateway` — in public subnet us-east-1a, uses EIP above

## Route Tables
- `aws_route_table` public — route `0.0.0.0/0` → internet gateway
- `aws_route_table_association` x2 — associate public route table with both public subnets
- `aws_route_table` private — route `0.0.0.0/0` → NAT gateway
- `aws_route_table_association` x2 — associate private route table with both private subnets

## Security Groups
- `aws_security_group` alb — inbound 443 from VPC CIDR (`10.0.0.0/16`), all outbound
- `aws_security_group` ecs — inbound 8000 from ALB security group only, all outbound
- `aws_security_group` lambda — no inbound, all outbound
- `aws_security_group` vpc_endpoints — inbound 443 from VPC CIDR, all outbound

## Application Load Balancer
- `aws_lb` — internal (`internal = true`), type application, in both public subnets, ALB security group
- `aws_lb_target_group` — port 8000, protocol HTTP, target type IP (required for Fargate), health check path `/health`
- `aws_lb_listener` — port 443 HTTPS, forward to target group (Cognito auth action added by auth/ module)

## VPC Endpoints (keep traffic within AWS network)
- `aws_vpc_endpoint` bedrock-runtime — Interface type, private DNS enabled
- `aws_vpc_endpoint` ecr-api — Interface type, private DNS enabled
- `aws_vpc_endpoint` ecr-dkr — Interface type, private DNS enabled
- `aws_vpc_endpoint` s3 — Gateway type, associated with private route table
- `aws_vpc_endpoint` dynamodb — Gateway type, associated with private route table
- `aws_vpc_endpoint` sqs — Interface type, private DNS enabled
- `aws_vpc_endpoint` secretsmanager — Interface type, private DNS enabled
- `aws_vpc_endpoint` ssm — Interface type, private DNS enabled
- `aws_vpc_endpoint` logs (CloudWatch) — Interface type, private DNS enabled
- `aws_vpc_endpoint` xray — Interface type, private DNS enabled

All Interface-type endpoints use the `vpc_endpoints` security group and are placed in private subnets.

## Outputs (consumed by other modules)
- `vpc_id`
- `public_subnet_ids` (list)
- `private_subnet_ids` (list)
- `alb_security_group_id`
- `ecs_security_group_id`
- `lambda_security_group_id`
- `alb_arn`
- `alb_target_group_arn`
- `alb_listener_arn`
