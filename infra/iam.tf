# ---------------------------------------------------------------------------
# strata-lambda-role
# Assumed by: all Lambda functions in the Strata platform account
# ---------------------------------------------------------------------------

resource "aws_iam_role" "strata_lambda" {
  name        = "strata-lambda-role"
  description = "Execution role for all Strata platform Lambda functions"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "LambdaAssumeRole"
      Effect = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action = "sts:AssumeRole"
    }]
  })

  tags = { Name = "strata-lambda-role" }
}

# Basic Lambda execution (CloudWatch Logs)
resource "aws_iam_role_policy_attachment" "lambda_basic_exec" {
  role       = aws_iam_role.strata_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_platform" {
  name = "strata-lambda-platform-policy"
  role = aws_iam_role.strata_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [

      # DynamoDB — clusters table (full access for orchestrator + status_checker)
      {
        Sid    = "DynamoDBClusters"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan",
        ]
        Resource = [
          aws_dynamodb_table.clusters.arn,
          "${aws_dynamodb_table.clusters.arn}/index/*",
        ]
      },

      # Secrets Manager — read/write only under strata/users/ namespace
      {
        Sid    = "SecretsManagerUserSecrets"
        Effect = "Allow"
        Action = [
          "secretsmanager:CreateSecret",
          "secretsmanager:PutSecretValue",
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret",
        ]
        Resource = "arn:aws:secretsmanager:${local.region}:${local.account_id}:secret:strata/users/*"
      },

      # Secrets Manager — read platform-level secrets (e.g. kms-key-arn)
      {
        Sid    = "SecretsManagerPlatform"
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue"]
        Resource = "arn:aws:secretsmanager:${local.region}:${local.account_id}:secret:strata/platform/*"
      },

      # KMS — use the master key for secret encryption/decryption
      {
        Sid    = "KMSUse"
        Effect = "Allow"
        Action = ["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"]
        Resource = aws_kms_key.strata.arn
      },

      # Step Functions — start executions (orchestrator Lambda)
      {
        Sid    = "StepFunctionsStart"
        Effect = "Allow"
        Action = ["states:StartExecution"]
        Resource = [
          "arn:aws:states:${local.region}:${local.account_id}:stateMachine:strata-provision-cluster",
          "arn:aws:states:${local.region}:${local.account_id}:stateMachine:strata-deprovision-cluster",
        ]
      },

      # Step Functions — send task token callbacks (start_codebuild Lambda)
      {
        Sid    = "StepFunctionsTaskCallback"
        Effect = "Allow"
        Action = [
          "states:SendTaskSuccess",
          "states:SendTaskFailure",
          "states:SendTaskHeartbeat",
        ]
        Resource = "*"
      },

      # STS — assume cross-account reader role in customer accounts
      {
        Sid    = "STSAssumeReader"
        Effect = "Allow"
        Action = ["sts:AssumeRole"]
        Resource = "arn:aws:iam::*:role/strata-platform-reader"
        Condition = {
          StringEquals = { "sts:ExternalId" = "strata-reader-v1" }
        }
      },

      # Cognito — update user attributes (verify-iam Lambda persists aws_account_id)
      {
        Sid    = "CognitoUpdateAttributes"
        Effect = "Allow"
        Action = ["cognito-idp:AdminUpdateUserAttributes"]
        Resource = aws_cognito_user_pool.strata.arn
      },

      # SSM — read platform parameters at runtime
      {
        Sid    = "SSMRead"
        Effect = "Allow"
        Action = ["ssm:GetParameter", "ssm:GetParameters"]
        Resource = "arn:aws:ssm:${local.region}:${local.account_id}:parameter/strata/*"
      },

      # Bedrock Agent runtime (agent_proxy Lambda)
      {
        Sid    = "BedrockAgentRuntime"
        Effect = "Allow"
        Action = ["bedrock:InvokeAgent"]
        Resource = "arn:aws:bedrock:${local.region}:${local.account_id}:agent-alias/*/*"
      },
    ]
  })
}

# ---------------------------------------------------------------------------
# strata-codebuild-role
# Assumed by: CodeBuild service (runs Terraform in customer accounts)
# ---------------------------------------------------------------------------

resource "aws_iam_role" "strata_codebuild" {
  name        = "strata-codebuild-role"
  description = "Service role for Strata CodeBuild projects (Terraform runner)"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "CodeBuildAssumeRole"
      Effect = "Allow"
      Principal = { Service = "codebuild.amazonaws.com" }
      Action = "sts:AssumeRole"
    }]
  })

  tags = { Name = "strata-codebuild-role" }
}

resource "aws_iam_role_policy" "codebuild_platform" {
  name = "strata-codebuild-platform-policy"
  role = aws_iam_role.strata_codebuild.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [

      # CloudWatch Logs — CodeBuild writes build logs
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws/codebuild/*"
      },

      # S3 — read Terraform code zips, write state + outputs
      {
        Sid    = "S3TerraformBuckets"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket",
        ]
        Resource = [
          aws_s3_bucket.tf_code.arn,
          "${aws_s3_bucket.tf_code.arn}/*",
          aws_s3_bucket.tf_state.arn,
          "${aws_s3_bucket.tf_state.arn}/*",
          aws_s3_bucket.outputs.arn,
          "${aws_s3_bucket.outputs.arn}/*",
        ]
      },

      # KMS — decrypt zips/state encrypted with Strata master key
      {
        Sid    = "KMSUse"
        Effect = "Allow"
        Action = ["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"]
        Resource = aws_kms_key.strata.arn
      },

      # Step Functions — send task success/failure after Terraform completes
      {
        Sid    = "StepFunctionsTaskToken"
        Effect = "Allow"
        Action = [
          "states:SendTaskSuccess",
          "states:SendTaskFailure",
          "states:SendTaskHeartbeat",
        ]
        Resource = "*"
      },

      # STS — assume provisioner role in customer accounts
      {
        Sid    = "STSAssumeProvisioner"
        Effect = "Allow"
        Action = ["sts:AssumeRole"]
        Resource = "arn:aws:iam::*:role/strata-platform-provisioner"
        Condition = {
          StringEquals = { "sts:ExternalId" = "strata-provisioner-v1" }
        }
      },

      # SSM — read Terraform-related parameters
      {
        Sid    = "SSMRead"
        Effect = "Allow"
        Action = ["ssm:GetParameter", "ssm:GetParameters"]
        Resource = "arn:aws:ssm:${local.region}:${local.account_id}:parameter/strata/*"
      },
    ]
  })
}

# ---------------------------------------------------------------------------
# strata-sfn-role
# Assumed by: Step Functions state machines
# ---------------------------------------------------------------------------

resource "aws_iam_role" "strata_sfn" {
  name        = "strata-sfn-role"
  description = "Execution role for Strata Step Functions state machines"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "SFNAssumeRole"
      Effect = "Allow"
      Principal = { Service = "states.amazonaws.com" }
      Action = "sts:AssumeRole"
    }]
  })

  tags = { Name = "strata-sfn-role" }
}

resource "aws_iam_role_policy" "sfn_platform" {
  name = "strata-sfn-platform-policy"
  role = aws_iam_role.strata_sfn.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [

      # DynamoDB — direct UpdateItem integration steps
      {
        Sid    = "DynamoDBUpdate"
        Effect = "Allow"
        Action = ["dynamodb:UpdateItem", "dynamodb:GetItem"]
        Resource = aws_dynamodb_table.clusters.arn
      },

      # Lambda — invoke start_codebuild, status_checker, argocd_deployer
      {
        Sid    = "InvokeLambda"
        Effect = "Allow"
        Action = ["lambda:InvokeFunction"]
        Resource = "arn:aws:lambda:${local.region}:${local.account_id}:function:strata-*"
      },

      # CloudWatch Logs — state machine execution logs
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogDelivery",
          "logs:GetLogDelivery",
          "logs:UpdateLogDelivery",
          "logs:DeleteLogDelivery",
          "logs:ListLogDeliveries",
          "logs:PutResourcePolicy",
          "logs:DescribeResourcePolicies",
          "logs:DescribeLogGroups",
        ]
        Resource = "*"
      },

      # X-Ray tracing
      {
        Sid    = "XRay"
        Effect = "Allow"
        Action = ["xray:PutTraceSegments", "xray:PutTelemetryRecords", "xray:GetSamplingRules", "xray:GetSamplingTargets"]
        Resource = "*"
      },
    ]
  })
}