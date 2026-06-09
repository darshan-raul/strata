# # ---------------------------------------------------------------------------
# # Outputs
# # ---------------------------------------------------------------------------

output "s3_tf_code_bucket"       { value = aws_s3_bucket.tf_code.id }
output "s3_tf_state_bucket"      { value = aws_s3_bucket.tf_state.id }
output "s3_outputs_bucket"       { value = aws_s3_bucket.outputs.id }
output "s3_agent_schemas_bucket" { value = aws_s3_bucket.agent_schemas.id }
output "s3_onboarding_cfn_bucket" { value = aws_s3_bucket.onboarding_cfn.id }
output "s3_web_app_bucket"       { value = aws_s3_bucket.web_app.id }
output "s3_web_app_website_url"  { value = aws_s3_bucket_website_configuration.web_app.website_endpoint }

# # ---------------------------------------------------------------------------
# # Outputs
# # ---------------------------------------------------------------------------

output "kms_key_arn"   { value = aws_kms_key.strata.arn }
output "kms_key_alias" { value = aws_kms_alias.strata.name }

# # ---------------------------------------------------------------------------
# # Outputs
# # ---------------------------------------------------------------------------

output "dynamodb_clusters_table_name" {
  value = aws_dynamodb_table.clusters.name
}

output "dynamodb_clusters_table_arn" {
  value = aws_dynamodb_table.clusters.arn
}

# # ---------------------------------------------------------------------------
# # Outputs — ARNs consumed by other Terraform files and the Lambda env var config
# # ---------------------------------------------------------------------------

output "lambda_role_arn"   { value = aws_iam_role.strata_lambda.arn }
output "codebuild_role_arn" { value = aws_iam_role.strata_codebuild.arn }
output "sfn_role_arn"      { value = aws_iam_role.strata_sfn.arn }


# # ---------------------------------------------------------------------------
# # Outputs
# # ---------------------------------------------------------------------------

output "cognito_user_pool_id" {
  value       = aws_cognito_user_pool.strata.id
  description = "Cognito User Pool ID"
}

output "cognito_client_id" {
  value       = aws_cognito_user_pool_client.flutter.id
  description = "Flutter app client ID"
}

output "cognito_domain" {
  value       = "https://${aws_cognito_user_pool_domain.strata.domain}.auth.${local.region}.amazoncognito.com"
  description = "Cognito hosted UI base URL"
}