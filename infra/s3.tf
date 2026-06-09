# ---------------------------------------------------------------------------
# Locals
# ---------------------------------------------------------------------------

locals {
  bucket_prefix = "strata"
}

# ---------------------------------------------------------------------------
# strata-tf-code  — Terraform module zips (one per provider)
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "tf_code" {
  bucket = "${local.bucket_prefix}-tf-code"
}

resource "aws_s3_bucket_versioning" "tf_code" {
  bucket = aws_s3_bucket.tf_code.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tf_code" {
  bucket = aws_s3_bucket.tf_code.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.strata.arn
    }
  }
}

resource "aws_s3_bucket_public_access_block" "tf_code" {
  bucket                  = aws_s3_bucket.tf_code.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ---------------------------------------------------------------------------
# strata-tf-state  — Per-cluster Terraform remote state
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "tf_state" {
  bucket = "${local.bucket_prefix}-tf-state"
}

resource "aws_s3_bucket_versioning" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.strata.arn
    }
  }
}

# Block public access to the tf_state bucket
resource "aws_s3_bucket_public_access_block" "tf_state" {
  bucket                  = aws_s3_bucket.tf_state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ---------------------------------------------------------------------------
# strata-outputs  — Per-cluster Terraform outputs (cluster_endpoint etc.)
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "outputs" {
  bucket = "${local.bucket_prefix}-outputs-${local.account_id}"
}

resource "aws_s3_bucket_versioning" "outputs" {
  bucket = aws_s3_bucket.outputs.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "outputs" {
  bucket = aws_s3_bucket.outputs.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.strata.arn
    }
  }
}

resource "aws_s3_bucket_public_access_block" "outputs" {
  bucket                  = aws_s3_bucket.outputs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ---------------------------------------------------------------------------
# strata-agent-schemas  — OpenAPI YAML files for Bedrock action groups
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "agent_schemas" {
  bucket = "${local.bucket_prefix}-agent-schemas"
}

resource "aws_s3_bucket_server_side_encryption_configuration" "agent_schemas" {
  bucket = aws_s3_bucket.agent_schemas.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.strata.arn
    }
  }
}

resource "aws_s3_bucket_public_access_block" "agent_schemas" {
  bucket                  = aws_s3_bucket.agent_schemas.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ---------------------------------------------------------------------------
# strata-onboarding-cfn  — Public-readable CFN template for customer onboarding
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "onboarding_cfn" {
  bucket = "${local.bucket_prefix}-onboarding-cfn"
}

resource "aws_s3_bucket_server_side_encryption_configuration" "onboarding_cfn" {
  bucket = aws_s3_bucket.onboarding_cfn.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256" # no KMS — object must be publicly readable
    }
  }
}

# Allow public GET on the CFN template (no secrets in the YAML)
resource "aws_s3_bucket_public_access_block" "onboarding_cfn" {
  bucket                  = aws_s3_bucket.onboarding_cfn.id
  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "onboarding_cfn_public_read" {
  bucket = aws_s3_bucket.onboarding_cfn.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "PublicRead"
      Effect    = "Allow"
      Principal = "*"
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.onboarding_cfn.arn}/*"
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.onboarding_cfn]
}

# Upload the CloudFormation template with StrataAccountId substituted at deploy time
resource "aws_s3_object" "onboarding_cfn_template" {
  bucket       = aws_s3_bucket.onboarding_cfn.id
  key          = "onboarding_cfn.yaml"
  source       = "${path.module}/../onboarding_cfn.yaml"
  content_type = "application/x-yaml"
  etag         = filemd5("${path.module}/../onboarding_cfn.yaml")
}

# ---------------------------------------------------------------------------
# strata-web-app  — Flutter Web static bundle (served via CloudFront in v2)
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "web_app" {
  bucket = "${local.bucket_prefix}-web-app-${local.account_id}"
  
}

resource "aws_s3_bucket_server_side_encryption_configuration" "web_app" {
  bucket = aws_s3_bucket.web_app.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_public_access_block" "web_app" {
  bucket                  = aws_s3_bucket.web_app.id
  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_website_configuration" "web_app" {
  bucket = aws_s3_bucket.web_app.id
  index_document { suffix = "index.html" }
  error_document { key = "index.html" } # SPA — all 404s → index.html
}

resource "aws_s3_bucket_policy" "web_app_public_read" {
  bucket = aws_s3_bucket.web_app.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "PublicRead"
      Effect    = "Allow"
      Principal = "*"
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.web_app.arn}/*"
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.web_app]
}

# ---------------------------------------------------------------------------
# SSM parameters — bucket names for Lambdas / CodeBuild
# ---------------------------------------------------------------------------

resource "aws_ssm_parameter" "tf_code_bucket" {
  name  = "/strata/s3/tf-code-bucket"
  type  = "String"
  value = aws_s3_bucket.tf_code.id
}

resource "aws_ssm_parameter" "tf_state_bucket" {
  name  = "/strata/s3/tf-state-bucket"
  type  = "String"
  value = aws_s3_bucket.tf_state.id
}

resource "aws_ssm_parameter" "outputs_bucket" {
  name  = "/strata/s3/outputs-bucket"
  type  = "String"
  value = aws_s3_bucket.outputs.id
}

