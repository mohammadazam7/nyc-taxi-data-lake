# One role per stage. Each can read the zones its stage reads and write only the zones
# it produces, for the configured taxi types. A bug in the model job cannot overwrite
# raw data, and the quality job, which only reports, cannot change any zone. The load
# job touches no zone at all: COPY reads the warehouse zone as the namespace's own
# role, so the job's role only needs to submit and watch statements in the workgroup.

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
    load = []
  }
  write_prefixes = {
    clean = flatten([
      for t in local.taxi_types : ["clean/${t}/", "clean/_runs/${t}/", "quarantine/${t}/"]
    ])
    model = flatten([
      for t in local.taxi_types : ["warehouse/${t}/", "warehouse/_runs/${t}/"]
    ])
    quality = [for t in local.taxi_types : "quality/${t}/"]
    load    = []
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

  dynamic "statement" {
    for_each = each.key == "load" ? [] : [distinct(concat(local.read_prefixes[each.key], local.write_prefixes[each.key]))]
    content {
      sid       = "ListLakePrefixes"
      actions   = ["s3:ListBucket"]
      resources = [local.lake_arn]
      condition {
        test     = "StringLike"
        variable = "s3:prefix"
        values   = [for p in statement.value : "${p}*"]
      }
    }
  }

  dynamic "statement" {
    for_each = each.key == "load" ? [] : [local.read_prefixes[each.key]]
    content {
      sid       = "ReadInputZones"
      actions   = ["s3:GetObject"]
      resources = [for p in statement.value : "${local.lake_arn}/${p}*"]
    }
  }

  # Spark overwrites a partition by deleting it and writing the new files, so the output
  # zones need delete as well as put.
  dynamic "statement" {
    for_each = each.key == "load" ? [] : [local.write_prefixes[each.key]]
    content {
      sid       = "WriteOutputZones"
      actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
      resources = [for p in statement.value : "${local.lake_arn}/${p}*"]
    }
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

  # The Data API authenticates as this role and maps it to a database user named
  # "IAMR:<role name>", which needs INSERT and DELETE on the star schema's tables.
  dynamic "statement" {
    for_each = each.key == "load" ? [var.load.workgroup_arn] : []
    content {
      sid       = "SubmitLoadStatements"
      actions   = ["redshift-data:BatchExecuteStatement", "redshift-serverless:GetCredentials"]
      resources = [statement.value]
    }
  }

  # These actions take no resource; the condition limits them to statements this role
  # submitted.
  dynamic "statement" {
    for_each = each.key == "load" ? [var.load.workgroup_arn] : []
    content {
      sid       = "WatchOwnStatements"
      actions   = ["redshift-data:DescribeStatement", "redshift-data:CancelStatement"]
      resources = ["*"]
      condition {
        test     = "StringEquals"
        variable = "redshift-data:statement-owner-iam-userid"
        values   = ["$${aws:userid}"]
      }
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
