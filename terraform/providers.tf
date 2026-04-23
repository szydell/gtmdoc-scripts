terraform {
  required_version = ">= 1.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Opcjonalnie: remote state w S3 (odkomentuj po bootstrapie)
  # backend "s3" {
  #   bucket  = "prod-mumps-pl-tfstate"
  #   key     = "mumps-pl/terraform.tfstate"
  #   region  = "eu-central-1"
  #   profile = "mumps-terraform"
  #   encrypt = true
  # }
}

# Provider główny — Frankfurt (S3, Route 53 są regionalne lub globalne)
provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile

  default_tags {
    tags = {
      Project     = "mumps-pl"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# Provider us-east-1 — wymagany dla certyfikatów ACM używanych przez CloudFront
provider "aws" {
  alias   = "us_east_1"
  region  = "us-east-1"
  profile = var.aws_profile

  default_tags {
    tags = {
      Project     = "mumps-pl"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
