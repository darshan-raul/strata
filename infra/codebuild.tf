resource "aws_codebuild_project" "provisioner" {
  name          = "strata-eks-provisioner"
  service_role  = aws_iam_role.strata_codebuild.arn

  source {
    type     = "S3"
    location = "${aws_s3_bucket.tf_code.id}/terraform-aws.zip"
  }

  artifacts {
    type = "NO_ARTIFACTS"
  }

  environment {
    compute_type = "BUILD_GENERAL1_SMALL"
    image        = "aws/codebuild/standard:7.0"
    type         = "LINUX_CONTAINER"

    environment_variable {
      name  = "TF_CODE_BUCKET"
      value = data.aws_ssm_parameter.tf_code_bucket.value
    }
    environment_variable {
      name  = "TF_STATE_BUCKET"
      value = data.aws_ssm_parameter.tf_state_bucket.value
    }
    environment_variable {
      name  = "OUTPUTS_BUCKET"
      value = data.aws_ssm_parameter.outputs_bucket.value
    }
  }

  logs_config {
    cloudwatch_logs {
      group_name = "/aws/codebuild/strata-eks-provisioner"
    }
  }
}