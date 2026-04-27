resource "aws_cognito_user_pool" "main" {
  name = "cognis-${var.environment}"

  password_policy {
    minimum_length    = 8
    require_uppercase = true
    require_lowercase = true
    require_numbers   = true
    require_symbols   = true
  }

  auto_verified_attributes = ["email"]

  tags = {
    Name        = "cognis-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_cognito_user_pool_client" "main" {
  name         = "cognis-${var.environment}-client"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret = false

  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["email", "openid", "profile"]
  allowed_oauth_flows_user_pool_client = true
  callback_urls                        = ["https://example.com/callback"]

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
