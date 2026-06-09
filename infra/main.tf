terraform {
  required_version = ">= 1.8.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.38"
    }
  }

  # Remote state — stored in a dedicated bucket that must be created manually
  # ONCE before the first apply:
  #   aws s3api create-bucket --bucket Strata-tf-bootstrap-state \
  #     --region ap-south-1 \
  #     --create-bucket-configuration LocationConstraint=ap-south-1
  #   aws s3api put-bucket-versioning --bucket Strata-tf-bootstrap-state \
  #     --versioning-configuration Status=Enabled
  backend "s3" {
    bucket  = "Strata-tf-bootstrap-state"
    key     = "infra/terraform.tfstate"
    region  = "ap-south-1"
    profile = "lab-user" #if not using default profile, else comment this
    encrypt = true
  }
}

provider "aws" {
  region = var.aws_region
  profile = "lab-user" # if not using default profile, else comment this 

  default_tags {
    tags = {
      Project     = "Strata"
      ManagedBy   = "terraform"
      Environment = var.environment
    }
  }
}


# ---------------------------------------------------------------------------
# Data sources
# ---------------------------------------------------------------------------

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# ---------------------------------------------------------------------------
# Locals
# ---------------------------------------------------------------------------

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name
}
