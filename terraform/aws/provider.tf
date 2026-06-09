terraform {
  required_version = ">= 1.8.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {}
}

provider "aws" {
  region = var.region

  assume_role {
    role_arn    = var.customer_role_arn
    external_id = var.external_id
  }

  default_tags {
    tags = {
      Project     = "strata-customer-cluster"
      ManagedBy   = "terraform"
      ClusterID   = var.cluster_id
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_availability_zones" "available" {
  state = "available"
}
