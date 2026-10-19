# One role per stage. Each can read the zones its stage reads and write only the zones
# it produces, for the configured taxi types. A bug in the model job cannot overwrite
# raw data, and the quality job, which only reports, cannot change any zone.

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

locals {
  taxi_types = sort(tolist(var.taxi_types))

  # Prefixes in the lake bucket, by stage. Every prefix ends in "/".
  read_prefixes = {
    clean = [for t in local.taxi_types : "raw/${t}/"]
    model = concat(
      [for t in local.taxi_types : "clean/${t}/"],
      ["raw/reference/"],
    )
    quality = flatten([
      for t in local.taxi_types : ["raw/${t}/", "clean/${t}/", "quarantine/${t}/", "warehouse/${t}/"]
    ])
  }
  write_prefixes = {
    clean = flatten([
      for t in local.taxi_types : ["clean/${t}/", "clean/_runs/${t}/", "quarantine/${t}/"]
    ])
    model = flatten([
      for t in local.taxi_types : ["warehouse/${t}/", "warehouse/_runs/${t}/"]
    ])
    quality = [for t in local.taxi_types : "quality/${t}/"]
  }
}

resource "aws_iam_role" "stage" {
  for_each = local.stages

  name               = "${var.name_prefix}-glue-${each.key}"
  assume_role_policy = data.aws_iam_policy_document.glue_assume.json
  tags               = var.tags
}

data "aws_iam_policy_document" "stage" {
  for_each = local.stages

  statement {
    sid       = "ListLakePrefixes"
    actions   = ["s3:ListBucket"]
    resources = [local.lake_arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        for p in distinct(concat(local.read_prefixes[each.key], local.write_prefixes[each.key])) : "${p}*"
      ]
    }
  }

  statement {
    sid       = "ReadInputZones"
    actions   = ["s3:GetObject"]
    resources = [for p in local.read_prefixes[each.key] : "${local.lake_arn}/${p}*"]
  }

  # Spark overwrites a partition by deleting it and writing the new files, so the output
  # zones need delete as well as put.
  statement {
    sid       = "WriteOutputZones"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = [for p in local.write_prefixes[each.key] : "${local.lake_arn}/${p}*"]
  }

  statement {
    sid     = "ReadJobArtifacts"
    actions = ["s3:GetObject"]
    resources = [
      "${local.artifacts_arn}/${local.script_key}",
      "${local.artifacts_arn}/${var.package_wheel_key}",
    ]
  }

  statement {
    sid       = "UseGlueTempDir"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${local.artifacts_arn}/glue-temp/*"]
  }

  statement {
    sid       = "ListGlueTempDir"
    actions   = ["s3:ListBucket"]
    resources = [local.artifacts_arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["glue-temp/*"]
    }
  }

  statement {
    sid = "WriteJobLogs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:${local.partition}:logs:${local.region}:${local.account_id}:log-group:/aws-glue/*"]
  }

  statement {
    sid       = "PublishJobMetrics"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["Glue"]
    }
  }

  dynamic "statement" {
    for_each = each.key == "quality" && var.alert_topic_arn != null ? [var.alert_topic_arn] : []
    content {
      sid       = "PublishQualityAlerts"
      actions   = ["sns:Publish"]
      resources = [statement.value]
    }
  }
}

resource "aws_iam_role_policy" "stage" {
  for_each = local.stages

  name   = "run-${each.key}"
  role   = aws_iam_role.stage[each.key].id
  policy = data.aws_iam_policy_document.stage[each.key].json
}
