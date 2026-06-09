# # ---------------------------------------------------------------------------
# # Secrets Manager — namespace for per-user cloud credentials
# # ---------------------------------------------------------------------------
# # Actual secret items are created dynamically by Lambda when users connect accounts.
# # Here we only create a resource policy that restricts who can read under strata/users/*

# resource "aws_secretsmanager_secret" "example_aws" {
#   # This is a placeholder / documentation object — real secrets are created by Lambda.
#   # Having one secret in TF ensures the namespace is established and the KMS key
#   # is associated before Lambda tries to write.
#   name        = "strata/platform/kms-key-arn"
#   description = "Stores the Strata KMS key ARN for reference by Lambda at runtime"
#   kms_key_id  = aws_kms_key.strata.arn

#   # Immediately store the KMS ARN as the secret value
#   # (Lambda reads this to encrypt new user secrets with the same key)
# }

# resource "aws_secretsmanager_secret_version" "example_aws" {
#   secret_id     = aws_secretsmanager_secret.example_aws.id
#   secret_string = jsonencode({ kms_key_arn = aws_kms_key.strata.arn })
# }

# # ---------------------------------------------------------------------------
# # SSM — KMS key ARN for Lambdas
# # ---------------------------------------------------------------------------

# resource "aws_ssm_parameter" "kms_key_arn" {
#   name  = "/strata/kms/master-key-arn"
#   type  = "String"
#   value = aws_kms_key.strata.arn
# }