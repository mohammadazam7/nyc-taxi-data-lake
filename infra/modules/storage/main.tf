# Three buckets:
#
#   lake      raw/, clean/, quarantine/, warehouse/, quality/ - the same layout the
#             pipeline writes locally under NYC_LAKE_ROOT, so the code needs one root.
#             Lifecycle rules work per prefix.
#   artifacts Glue job scripts, the package wheel and the TLC zone lookup.
#   athena    Athena query results, expired quickly.
#
# All are private, encrypted with S3-managed keys, and refuse plain-HTTP requests.

locals {
  buckets = {
    lake      = "${var.name_prefix}-lake"
    artifacts = "${var.name_prefix}-artifacts"
    athena    = "${var.name_prefix}-athena-results"
  }
}

resource "aws_s3_bucket" "this" {
  for_each = local.buckets

  bucket        = each.value
  force_destroy = var.force_destroy
  tags          = merge(var.tags, { "nyc-lake:bucket" = each.key })
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each = aws_s3_bucket.this

  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "this" {
  for_each = aws_s3_bucket.this

  bucket = each.value.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = aws_s3_bucket.this

  bucket = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

data "aws_iam_policy_document" "tls_only" {
  for_each = aws_s3_bucket.this

  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      each.value.arn,
      "${each.value.arn}/*",
    ]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "tls_only" {
  for_each = aws_s3_bucket.this

  bucket = each.value.id
  policy = data.aws_iam_policy_document.tls_only[each.key].json

  # A bucket policy cannot be attached while the public access block is being created.
  depends_on = [aws_s3_bucket_public_access_block.this]
}

# Versioning on the lake bucket protects raw data from an accidental overwrite. The
# derived zones are rebuilt in place by design, so their old versions expire quickly.
resource "aws_s3_bucket_versioning" "lake" {
  bucket = aws_s3_bucket.this["lake"].id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "lake" {
  bucket = aws_s3_bucket.this["lake"].id

  rule {
    id     = "raw-tiering"
    status = "Enabled"
    filter {
      prefix = "raw/"
    }
    transition {
      days          = var.raw_glacier_days
      storage_class = "GLACIER_IR"
    }
    noncurrent_version_expiration {
      noncurrent_days = var.raw_noncurrent_days
    }
  }

  rule {
    id     = "quarantine-expiry"
    status = "Enabled"
    filter {
      prefix = "quarantine/"
    }
    expiration {
      days = var.quarantine_expiry_days
    }
    noncurrent_version_expiration {
      noncurrent_days = 1
    }
  }

  # clean/, warehouse/ and quality/ are overwritten on every rerun; keep a day of old
  # versions for a quick rollback and no more.
  dynamic "rule" {
    for_each = toset(["clean/", "warehouse/", "quality/"])
    content {
      id     = "${trimsuffix(rule.value, "/")}-noncurrent"
      status = "Enabled"
      filter {
        prefix = rule.value
      }
      noncurrent_version_expiration {
        noncurrent_days = 1
      }
    }
  }

  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 2
    }
  }

  depends_on = [aws_s3_bucket_versioning.lake]
}

resource "aws_s3_bucket_lifecycle_configuration" "athena" {
  bucket = aws_s3_bucket.this["athena"].id

  rule {
    id     = "expire-results"
    status = "Enabled"
    filter {}
    expiration {
      days = var.athena_results_expiry_days
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}
