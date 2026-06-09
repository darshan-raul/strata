resource "aws_apigatewayv2_api" "Strata" {
  name          = "Strata-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["*"]
    allow_headers = ["*"]
  }
}

resource "aws_apigatewayv2_authorizer" "jwt" {
  api_id           = aws_apigatewayv2_api.Strata.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "cognito-jwt"

  jwt_configuration {
    audience = [aws_cognito_user_pool_client.flutter.id]
    issuer   = "https://cognito-idp.${local.region}.amazonaws.com/${aws_cognito_user_pool.Strata.id}"
  }
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.Strata.id
  name        = "$default"
  auto_deploy = true
}

# ---
# Routes
# ---

# POST /clusters
resource "aws_apigatewayv2_route" "post_clusters" {
  api_id    = aws_apigatewayv2_api.Strata.id
  route_key = "POST /clusters"

  target             = "integrations/${aws_apigatewayv2_integration.orchestrator.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt.id
}

# GET /clusters/{cluster_id}
resource "aws_apigatewayv2_route" "get_cluster" {
  api_id    = aws_apigatewayv2_api.Strata.id
  route_key = "GET /clusters/{cluster_id}"

  target             = "integrations/${aws_apigatewayv2_integration.orchestrator.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt.id
}

# ---
# Integrations
# ---

resource "aws_apigatewayv2_integration" "orchestrator" {
  api_id                 = aws_apigatewayv2_api.Strata.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.orchestrator.invoke_arn
  payload_format_version = "2.0"
}

# ---
# Outputs
# ---

output "api_gateway_invoke_url" {
  value = aws_apigatewayv2_api.Strata.api_endpoint
}
