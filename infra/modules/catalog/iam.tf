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
  catalog_arn = "arn:${local.partition}:glue:${local.region}:${local.account_id}:catalog"
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
    resources = concat(
      [local.catalog_arn],
      [for db in aws_glue_catalog_database.this : db.arn],
      [for db in aws_glue_catalog_database.this : "arn:${local.partition}:glue:${local.region}:${local.account_id}:table/${db.name}/*"],
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
