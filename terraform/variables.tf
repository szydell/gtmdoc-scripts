variable "aws_profile" {
  description = "Nazwa profilu AWS CLI do użycia przez Terraform"
  type        = string
  default     = "mumps-terraform"
}

variable "aws_region" {
  description = "Region główny (S3 bucket, Route 53)"
  type        = string
  default     = "eu-central-1"
}

variable "environment" {
  description = "Nazwa środowiska (prod / staging)"
  type        = string
  default     = "prod"
}

variable "domain_name" {
  description = "Główna domena serwisu"
  type        = string
  default     = "mumps.pl"
}

variable "bucket_name" {
  description = "Nazwa bucketu S3 ze statyczną treścią"
  type        = string
  default     = "prod-mumps-pl"
}

variable "price_class" {
  description = "Klasa cenowa CloudFront (PriceClass_100 = tylko Europa + USA — najtaniej)"
  type        = string
  default     = "PriceClass_All"
}

variable "web_acl_id" {
  description = "ARN Web ACL (WAFv2) powiązanego z dystrybucją CloudFront; pusty string = brak WAF"
  type        = string
  default     = ""
}
