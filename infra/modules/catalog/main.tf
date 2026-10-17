# Glue Data Catalog for the lake, crawlers that keep it in step with S3, and an Athena
# workgroup to query it.
#
# Crawlers only register tables and partitions. The pipeline writes a fixed schema, so
# a crawler that sees a changed schema logs it instead of rewriting the table.

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition
  region     = data.aws_region.current.name
  lake_arn   = "arn:${local.partition}:s3:::${var.lake_bucket}"

  # Glue database names allow only lowercase letters, digits and underscores.
  db_prefix = replace(var.name_prefix, "-", "_")
  databases = {
    raw       = "${local.db_prefix}_raw"
    clean     = "${local.db_prefix}_clean"
    warehouse = "${local.db_prefix}_warehouse"
  }

  # Bookkeeping files the pipeline writes next to the data.
  crawler_exclusions = ["_runs/**", "**/_manifest.json", "**/_SUCCESS", "**.crc"]
}

resource "aws_glue_catalog_database" "this" {
  for_each = local.databases

  name        = each.value
  description = "NYC taxi lake, ${each.key} zone."
  tags        = var.tags
}

# raw/<taxi>/year=/month=/ and clean/<taxi>/pickup_date=/ each become one partitioned
# table per taxi type, named after the folder.
resource "aws_glue_crawler" "raw" {
  name          = "${var.name_prefix}-raw"
  role          = aws_iam_role.crawler.arn
  database_name = aws_glue_catalog_database.this["raw"].name
  tags          = var.tags

  dynamic "s3_target" {
    for_each = var.taxi_types
    content {
      path       = "s3://${var.lake_bucket}/raw/${s3_target.value}/"
      exclusions = local.crawler_exclusions
    }
  }

  # Months are only ever added, so crawl just the new partitions.
  recrawl_policy {
    recrawl_behavior = "CRAWL_NEW_FOLDERS_ONLY"
  }

  schema_change_policy {
    update_behavior = "LOG"
    delete_behavior = "LOG"
  }
}

resource "aws_glue_crawler" "clean" {
  name          = "${var.name_prefix}-clean"
  role          = aws_iam_role.crawler.arn
  database_name = aws_glue_catalog_database.this["clean"].name
  tags          = var.tags

  dynamic "s3_target" {
    for_each = var.taxi_types
    content {
      path       = "s3://${var.lake_bucket}/clean/${s3_target.value}/"
      exclusions = local.crawler_exclusions
    }
  }

  recrawl_policy {
    recrawl_behavior = "CRAWL_NEW_FOLDERS_ONLY"
  }

  schema_change_policy {
    update_behavior = "LOG"
    delete_behavior = "LOG"
  }
}

# warehouse/<taxi>/<table>/ holds one folder per star-schema table. Table level 4
# (bucket / warehouse / taxi / table) makes each folder its own table rather than one
# merged table. One crawler per taxi type, so the tables can be prefixed with it
# (yellow_fact_trips) instead of colliding.
resource "aws_glue_crawler" "warehouse" {
  for_each = var.taxi_types

  name          = "${var.name_prefix}-warehouse-${each.value}"
  role          = aws_iam_role.crawler.arn
  database_name = aws_glue_catalog_database.this["warehouse"].name
  table_prefix  = "${each.value}_"
  tags          = var.tags

  s3_target {
    path       = "s3://${var.lake_bucket}/warehouse/${each.value}/"
    exclusions = local.crawler_exclusions
  }

  configuration = jsonencode({
    Version  = 1.0
    Grouping = { TableLevelConfiguration = 4 }
  })

  # Dimensions are rewritten in full on every run, so look at everything each time.
  recrawl_policy {
    recrawl_behavior = "CRAWL_EVERYTHING"
  }

  schema_change_policy {
    update_behavior = "LOG"
    delete_behavior = "LOG"
  }
}

resource "aws_athena_workgroup" "this" {
  name          = var.name_prefix
  description   = "Ad-hoc queries over the NYC taxi lake."
  force_destroy = true
  tags          = var.tags

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = var.athena_bytes_scanned_cutoff

    engine_version {
      selected_engine_version = "Athena engine version 3"
    }

    result_configuration {
      output_location = "s3://${var.athena_results_bucket}/results/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}
