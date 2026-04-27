output "vpc_id" {
  value = aws_vpc.main.id
}

output "subnet_ids" {
  value = aws_subnet.public[*].id
}

output "alb_security_group_id" {
  value = aws_security_group.alb.id
}

output "ecs_security_group_id" {
  value = aws_security_group.ecs.id
}

output "lambda_security_group_id" {
  value = aws_security_group.lambda.id
}

output "alb_arn" {
  value = aws_lb.main.arn
}

output "alb_target_group_arn" {
  value = aws_lb_target_group.main.arn
}

output "alb_listener_arn" {
  value = aws_lb_listener.https.arn
}

output "alb_dns_name" {
  value = aws_lb.main.dns_name
}
