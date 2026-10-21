# The role Redshift assumes to run COPY: read the warehouse zone, nothing else.

data "aws_iam_policy_document" "redshift_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["redshift.amazonaws.com", "redshift-serverless.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "copy" {
  name               = "${var.name_prefix}-redshift-copy"
  assume_role_policy = data.aws_iam_policy_document.redshift_assume.json
  tags               = var.tags
}

locals {
  warehouse_prefixes = [for t in var.taxi_types : "warehouse/${t}/"]
}

data "aws_iam_policy_document" "copy" {
  statement {
    sid       = "ListWarehouseZone"
    actions   = ["s3:ListBucket"]
    resources = [local.lake_arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = [for p in local.warehouse_prefixes : "${p}*"]
    }
  }

  statement {
    sid       = "ReadWarehouseZone"
    actions   = ["s3:GetObject"]
    resources = [for p in local.warehouse_prefixes : "${local.lake_arn}/${p}*"]
  }
}

resource "aws_iam_role_policy" "copy" {
  name   = "read-warehouse-zone"
  role   = aws_iam_role.copy.id
  policy = data.aws_iam_policy_document.copy.json
}
