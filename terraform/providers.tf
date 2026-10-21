terraform {
  # 1.10+ for S3-native state locking (use_lockfile) - no DynamoDB table needed.
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state, so the team shares one state file with locking. Settings come from
  # a backend config file kept out of Git:  terraform init -backend-config=backend.hcl
  # (see backend.hcl.example).
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "aegis-enterprise-ai"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}
