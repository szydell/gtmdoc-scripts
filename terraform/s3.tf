# ---------------------------------------------------------------------------
# S3 — statyczny hosting Hugo (brak publicznego dostępu; tylko przez CloudFront OAC)
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "site" {
  bucket = var.bucket_name
}

# Zablokuj każdy publiczny dostęp — ruch przychodzi wyłącznie przez CloudFront
resource "aws_s3_bucket_public_access_block" "site" {
  bucket = aws_s3_bucket.site.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Wersjonowanie — ułatwia rollback po przypadkowym nadpisaniu
resource "aws_s3_bucket_versioning" "site" {
  bucket = aws_s3_bucket.site.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Szyfrowanie w spoczynku (SSE-S3 — bez dodatkowych kosztów KMS)
resource "aws_s3_bucket_server_side_encryption_configuration" "site" {
  bucket = aws_s3_bucket.site.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Polityka bucket — pozwala tylko CloudFront OAC na GetObject
resource "aws_s3_bucket_policy" "site" {
  bucket = aws_s3_bucket.site.id
  policy = data.aws_iam_policy_document.s3_cloudfront_oac.json

  # Politykę można ustawić dopiero po wyłączeniu publicznego dostępu
  depends_on = [aws_s3_bucket_public_access_block.site]
}

data "aws_iam_policy_document" "s3_cloudfront_oac" {
  statement {
    sid    = "AllowCloudFrontServicePrincipal"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.site.arn}/*"]

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.site.arn]
    }
  }
}
