output "github_actions_role_arn" {
  value = aws_iam_role.github_actions_role.arn
}

output "self_signed_cert_arn" {
  value = aws_acm_certificate.self_signed.arn
}
