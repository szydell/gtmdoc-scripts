# ---------------------------------------------------------------------------
# CloudFront — dystrybucja z OAC (Origin Access Control, nowsze niż OAI)
# ---------------------------------------------------------------------------

# OAC — kontrola dostępu do S3 bez publicznego URL bucketu
resource "aws_cloudfront_origin_access_control" "site" {
  name                              = "${var.bucket_name}-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "${var.domain_name} — static site"
  default_root_object = "index.html"
  price_class         = var.price_class
  aliases             = [var.domain_name, "www.${var.domain_name}"]

  # Źródło — S3 bucket (dostęp przez OAC, nie publiczny URL)
  origin {
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_id                = "s3-${var.bucket_name}"
    origin_access_control_id = aws_cloudfront_origin_access_control.site.id
  }

  # Zachowanie domyślne — wszystkie requesty do S3
  default_cache_behavior {
    target_origin_id       = "s3-${var.bucket_name}"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]

    # Managed cache policy: CachingOptimized (AWS managed, ID stały)
    cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"

    # Managed origin request policy: S3Origin (nie przesyła nagłówków do S3)
    origin_request_policy_id = "88a5eaf4-2fd4-4709-b370-b4c650ea3fcf"
  }

  # Strony błędów — Hugo SPA / statyczny routing
  custom_error_response {
    error_code            = 403
    response_code         = 404
    response_page_path    = "/404.html"
    error_caching_min_ttl = 10
  }

  custom_error_response {
    error_code            = 404
    response_code         = 404
    response_page_path    = "/404.html"
    error_caching_min_ttl = 10
  }

  # Certyfikat ACM (us-east-1) — TLS terminowany na edge
  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.site.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }
}
