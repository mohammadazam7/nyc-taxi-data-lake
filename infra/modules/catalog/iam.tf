# The crawlers' role: read the zones they crawl, write their own database's tables and
# partitions, and log. Nothing else - no writes to S3, no other databases.

data "aws_iam_policy_document" "glue_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "crawler" {
  name               = "${var.name_prefix}-glue-crawler"
  assume_role_policy = data.aws_iam_policy_document.glue_assume.json
  tags               = var.tags
}

locals {
  crawled_prefixes = flatten([
    for zone in ["raw", "clean", "warehouse"] : [for t in var.taxi_types : "${zone}/${t}/"]
  ])
  glue_arn_prefix = "arn:${local.partition}:glue:${local.region}:${local.account_id}"
  catalog_arn     = "${local.glue_arn_prefix}:catalog"
}

data "aws_iam_policy_document" "crawler" {
  statement {
    sid       = "ListCrawledPrefixes"
    actions   = ["s3:ListBucket"]
    resources = [local.lake_arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = [for p in local.crawled_prefixes : "${p}*"]
    }
  }

  statement {
    sid       = "ReadCrawledObjects"
    actions   = ["s3:GetObject"]
    resources = [for p in local.crawled_prefixes : "${local.lake_arn}/${p}*"]
  }

  statement {
    sid = "ManageLakeTables"
    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetTables",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:BatchGetPartition",
      "glue:CreatePartition",
      "glue:BatchCreatePartition",
      "glue:UpdatePartition",
      "glue:BatchUpdatePartition",
    ]
    # Built from the names rather than the resources' ARNs, so the policy is known at
    # plan time.
    resources = concat(
      [local.catalog_arn],
      [for name in values(local.databases) : "${local.glue_arn_prefix}:database/${name}"],
      [for name in values(local.databases) : "${local.glue_arn_prefix}:table/${name}/*"],
    )
  }

  statement {
    sid = "WriteCrawlerLogs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:${local.partition}:logs:${local.region}:${local.account_id}:log-group:/aws-glue/crawlers*"]
  }
}

resource "aws_iam_role_policy" "crawler" {
  name   = "crawl-lake"
  role   = aws_iam_role.crawler.id
  policy = data.aws_iam_policy_document.crawler.json
}
