resource "aws_cognito_user_pool" "main" {
  name = "cognis-${var.environment}"

  password_policy {
    minimum_length                   = 8
    require_uppercase                = true
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    temporary_password_validity_days = 7
  }

  auto_verified_attributes = ["email"]

  mfa_configuration = "OPTIONAL"

  software_token_mfa_configuration {
    enabled = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  deletion_protection = var.deletion_protection ? "ACTIVE" : "INACTIVE"

  tags = {
    Name        = "cognis-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_cognito_user_pool_client" "main" {
  name         = "cognis-${var.environment}-client"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret = true

  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["email", "openid", "profile"]
  allowed_oauth_flows_user_pool_client = true

  callback_urls = ["https://${var.frontend_domain}/callback"]
  logout_urls   = ["https://${var.frontend_domain}/logout"]

  supported_identity_providers = ["COGNITO"]

  access_token_validity  = 60
  refresh_token_validity = 30
  id_token_validity      = 60

  token_validity_units {
    access_token  = "minutes"
    refresh_token = "days"
    id_token      = "minutes"
  }
}

resource "aws_cognito_user_pool_domain" "main" {
  domain       = "cognis-${var.environment}"
  user_pool_id = aws_cognito_user_pool.main.id
}

resource "aws_lb_listener_rule" "auth" {
  listener_arn = var.alb_listener_arn
  priority     = 100

  action {
    type  = "authenticate-cognito"
    order = 1
    authenticate_cognito {
      user_pool_arn              = aws_cognito_user_pool.main.arn
      user_pool_client_id        = aws_cognito_user_pool_client.main.id
      user_pool_domain           = aws_cognito_user_pool_domain.main.domain
      on_unauthenticated_request = "authenticate"
    }
  }

  action {
    type             = "forward"
    order            = 2
    target_group_arn = var.alb_target_group_arn
  }

  condition {
    path_pattern {
      values = ["/*"]
    }
  }
}
