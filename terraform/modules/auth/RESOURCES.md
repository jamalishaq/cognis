# auth/ — Resources to Provision

## Cognito User Pool
- `aws_cognito_user_pool` — name `cognis-${var.environment}`
- Password policy: min length 8, require uppercase, lowercase, numbers, symbols
- `auto_verified_attributes = ["email"]`
- MFA: optional (not enforced for capstone)
- Account recovery: email only
- `deletion_protection = "ACTIVE"` in prod

## Cognito User Pool Client
- `aws_cognito_user_pool_client` — name `cognis-${var.environment}-client`
- `generate_secret = false` (SPA client — no server-side secret needed)
- Allowed OAuth flows: `code`
- Allowed OAuth scopes: `email`, `openid`, `profile`
- Callback URLs: `https://${var.frontend_domain}/callback`
- Logout URLs: `https://${var.frontend_domain}/logout`
- Token validity:
  - `access_token_validity = 60` (minutes — 1 hour)
  - `refresh_token_validity = 30` (days)
  - `id_token_validity = 60` (minutes)

## Cognito User Pool Domain
- `aws_cognito_user_pool_domain` — domain `cognis-${var.environment}` (Cognito hosted UI)

## ALB Cognito Authentication
- `aws_lb_listener_rule` on ALB listener (from networking module):
  - Action type: `authenticate-cognito`
  - `user_pool_arn`, `user_pool_client_id`, `user_pool_domain` from above resources
  - `on_unauthenticated_request = "authenticate"` — redirect to Cognito login
  - Forward to ECS target group after successful auth

## Outputs
- `user_pool_id`
- `user_pool_arn`
- `user_pool_client_id`
- `user_pool_domain`
- `cognito_endpoint`
