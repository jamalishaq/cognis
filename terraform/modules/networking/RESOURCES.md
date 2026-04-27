# networking/ — Resources to Provision (Capstone)

> **Note:** This is the simplified capstone networking setup. All production hardening decisions (private subnets, NAT Gateway, VPC Endpoints, IP allowlisting, Cognito on ALB) are documented in DECISIONS.md under VPC & Networking — Future Implementation and deferred to production.

## VPC
- `aws_vpc` — CIDR `10.0.0.0/16`, DNS hostnames enabled, DNS resolution enabled

## Public Subnets (ECS runs here with public IPs)
- `aws_subnet` x2 — `10.0.1.0/24` (us-east-1a), `10.0.2.0/24` (us-east-1b)
- `map_public_ip_on_launch = true` — ECS tasks get public IPs and reach AWS services directly

## Internet Gateway
- `aws_internet_gateway` — attached to VPC
- `aws_route_table` — route `0.0.0.0/0` → internet gateway
- `aws_route_table_association` x2 — associate route table with both subnets

## Security Groups
- `aws_security_group` alb — inbound 443 from `0.0.0.0/0`, outbound all to ECS security group
- `aws_security_group` ecs — inbound 8000 from ALB security group only, outbound all
- `aws_security_group` lambda — no inbound, outbound all

## Application Load Balancer
- `aws_lb` — internet-facing (`internal = false`), type application, in both subnets, ALB security group
- `aws_lb_target_group` — port 8000, protocol HTTP, target type IP, health check path `/health`
- `aws_lb_listener` — port 443 HTTPS, forward all traffic to ECS target group

## ACM Certificate
- `aws_acm_certificate` — for the ALB HTTPS listener. Use DNS validation.
- `aws_acm_certificate_validation` — validate via Route53 or manual DNS record

## Outputs
- `vpc_id`
- `subnet_ids` (list of both public subnets)
- `alb_security_group_id`
- `ecs_security_group_id`
- `lambda_security_group_id`
- `alb_arn`
- `alb_target_group_arn`
- `alb_listener_arn`
- `alb_dns_name` — the public DNS name engineers and alerting tools use to reach the system
