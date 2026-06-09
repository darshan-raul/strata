# ---------------------------------------------------------------------------
# Cognito User Pool
# ---------------------------------------------------------------------------

resource "aws_cognito_user_pool" "Strata" {
  name = "Strata-platform-users"

  # Email is the primary identifier
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length                   = 8
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = false
    require_lowercase                = true
    temporary_password_validity_days = 7
  }

  # Verification email
  verification_message_template {
    default_email_option = "CONFIRM_WITH_CODE"
    email_subject        = "Observatory — Verify your email"
    email_message        = "Your verification code is {####}"
  }

  # Account recovery via email
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  # Custom attributes stored per user
  schema {
    name                     = "github_token"
    attribute_data_type      = "String"
    mutable                  = true
    developer_only_attribute = false
    string_attribute_constraints {
      min_length = 0
      max_length = 2048
    }
  }

  schema {
    name                     = "aws_account_id"
    attribute_data_type      = "String"
    mutable                  = true
    developer_only_attribute = false
    string_attribute_constraints {
      min_length = 12
      max_length = 12
    }
  }

  # Allow admin to update user attributes (used by verify-iam Lambda)
  admin_create_user_config {
    allow_admin_create_user_only = false
  }

  tags = {
    Name = "Strata-platform-users"
  }
}

# ---------------------------------------------------------------------------
# User Pool Client — Flutter Android + Web
# ---------------------------------------------------------------------------

resource "aws_cognito_user_pool_client" "flutter" {
  name         = "observatory-flutter"
  user_pool_id = aws_cognito_user_pool.Strata.id

  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_PASSWORD_AUTH", # useful for testing; remove for pure SRP prod
  ]

  # OAuth / hosted-UI settings (used for GitHub redirect)
  callback_urls = [
    "Strata://callback",      # Android deep-link
    "http://localhost:8080", # Flutter web dev #temp, move to main url
  ]
  logout_urls = [
    "Strata://logout",
    "http://localhost:8080/logout",
  ]

  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  allowed_oauth_flows_user_pool_client = true
  generate_secret                      = false

  # Token validity
  access_token_validity  = 1   # hours
  id_token_validity      = 1   # hours
  refresh_token_validity = 30  # days

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }

  # Prevent user existence errors leaking in auth responses
  prevent_user_existence_errors = "ENABLED"

  read_attributes = [
    "email",
    "email_verified",
    "custom:github_token",
    "custom:aws_account_id",
  ]

  write_attributes = [
    "email",
    "custom:github_token",
    "custom:aws_account_id",
  ]
}

# ---------------------------------------------------------------------------
# User Pool Domain (needed for hosted UI / GitHub OAuth redirect)
# ---------------------------------------------------------------------------

resource "aws_cognito_user_pool_domain" "Strata" {
  domain       = "Strata-observatory-${local.account_id}"
  user_pool_id = aws_cognito_user_pool.Strata.id
}

# ---------------------------------------------------------------------------
# SSM Parameters — consumed by Lambdas + Flutter app config
# ---------------------------------------------------------------------------

resource "aws_ssm_parameter" "cognito_user_pool_id" {
  name  = "/Strata/cognito/user-pool-id"
  type  = "String"
  value = aws_cognito_user_pool.Strata.id
}

resource "aws_ssm_parameter" "cognito_client_id" {
  name  = "/Strata/cognito/client-id"
  type  = "String"
  value = aws_cognito_user_pool_client.flutter.id
}

resource "aws_ssm_parameter" "platform_account_id" {
  name        = "/Strata/platform-account-id"
  type        = "String"
  value       = local.account_id
  description = "Strata platform AWS account ID — embedded in onboarding CFN template"
}


