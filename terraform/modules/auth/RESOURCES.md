# auth/ — Resources to Provision (Capstone)

> **Note:** Cognito authentication on the ALB is deferred to production. For the capstone all endpoints are publicly accessible — no auth enforced at the infrastructure level. The `AUTH_DISABLED=true` behaviour is built into FastAPI via the `auth_disabled` config flag.

## Cognito User Pool (provision but not enforced on ALB)
- `aws_cognito_user_pool` — name `cognis-${var.environment}`
- Password policy: min length 8, require uppercase, lowercase, numbers, symbols
- `auto_verified_attributes = ["email"]`

## Cognito User Pool Client
- `aws_cognito_user_pool_client` — name `cognis-${var.environment}-client`
- `generate_secret = false`
- Allowed OAuth flows: `code`
- Allowed OAuth scopes: `email`, `openid`, `profile`
- Token validity:
  - `access_token_validity = 60` (minutes)
  - `refresh_token_validity = 30` (days)
  - `id_token_validity = 60` (minutes)

## Cognito User Pool Domain
- `aws_cognito_user_pool_domain` — domain `cognis-${var.environment}`

> ALB authentication rule is NOT provisioned for capstone. Add it in production by configuring an `authenticate-cognito` action on the ALB listener in the networking module.

## Future Implementation (production)
- ALB listener rule with `authenticate-cognito` action on all non-`/analyse` paths
- `on_unauthenticated_request = "authenticate"` — redirect to Cognito login
- IP allowlist rule on `/analyse` path — restrict to alerting tool CIDR ranges

## Outputs
- `user_pool_id`
- `user_pool_arn`
- `user_pool_client_id`
- `user_pool_domain`
