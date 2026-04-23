# ---------------------------------------------------------------------------
# Route 53 — hosted zone + rekordy DNS dla mumps.pl
# ---------------------------------------------------------------------------

# Strefa — po `terraform apply` odczytaj z outputs.tf serwery NS
# i podaj je u swojego rejestratora domeny (zastąpi obecne NS)
resource "aws_route53_zone" "site" {
  name = var.domain_name
}

# Rekord A — apex (mumps.pl) → CloudFront (alias, brak TTL)
resource "aws_route53_record" "apex" {
  zone_id = aws_route53_zone.site.zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}

# Rekord AAAA — apex IPv6
resource "aws_route53_record" "apex_aaaa" {
  zone_id = aws_route53_zone.site.zone_id
  name    = var.domain_name
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}

# Rekord A — www.mumps.pl → CloudFront
resource "aws_route53_record" "www" {
  zone_id = aws_route53_zone.site.zone_id
  name    = "www.${var.domain_name}"
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}

# Rekord AAAA — www IPv6
resource "aws_route53_record" "www_aaaa" {
  zone_id = aws_route53_zone.site.zone_id
  name    = "www.${var.domain_name}"
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}
