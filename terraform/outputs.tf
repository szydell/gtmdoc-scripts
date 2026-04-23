output "s3_bucket_name" {
  description = "Nazwa bucketu S3"
  value       = aws_s3_bucket.site.id
}

output "s3_bucket_arn" {
  description = "ARN bucketu S3"
  value       = aws_s3_bucket.site.arn
}

output "cloudfront_domain" {
  description = "Domena CloudFront (*.cloudfront.net) — przydatna do testów przed przełączeniem DNS"
  value       = aws_cloudfront_distribution.site.domain_name
}

output "cloudfront_distribution_id" {
  description = "ID dystrybucji CloudFront (potrzebny do invalidacji cache: aws cloudfront create-invalidation)"
  value       = aws_cloudfront_distribution.site.id
}

output "cloudfront_distribution_arn" {
  description = "ARN dystrybucji CloudFront"
  value       = aws_cloudfront_distribution.site.arn
}

output "acm_certificate_arn" {
  description = "ARN certyfikatu ACM (us-east-1)"
  value       = aws_acm_certificate.site.arn
}

output "route53_zone_id" {
  description = "ID strefy Route 53"
  value       = aws_route53_zone.site.zone_id
}

output "route53_nameservers" {
  description = <<-EOT
    *** WAŻNE — te 4 serwery NS podaj u swojego rejestratora domeny (np. OVH, nazwa.pl) ***
    Zastąp nimi obecne NS rekordy dla mumps.pl.
    Po zmianie propagacja DNS może potrwać do 48h (zwykle kilka minut).
  EOT
  value = aws_route53_zone.site.name_servers
}

output "site_url" {
  description = "Publiczny URL serwisu"
  value       = "https://${var.domain_name}"
}
