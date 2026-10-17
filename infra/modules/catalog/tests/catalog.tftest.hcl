# Plan-only tests with a mocked provider: they need no AWS credentials.

mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
  mock_data "aws_region" {
    defaults = { name = "us-east-1" }
  }
  # Mocked documents still have to be valid policy JSON for the role to plan.
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
}

variables {
  name_prefix           = "nyc-lake-test"
  lake_bucket           = "nyc-lake-test-lake"
  athena_results_bucket = "nyc-lake-test-athena-results"
}

run "one_database_per_zone" {
  command = plan

  assert {
    condition = toset([for db in aws_glue_catalog_database.this : db.name]) == toset([
      "nyc_lake_test_raw",
      "nyc_lake_test_clean",
      "nyc_lake_test_warehouse",
    ])
    error_message = "database names must be per zone with underscores"
  }
}

run "crawlers_target_each_taxi_type" {
  command = plan

  variables {
    taxi_types = ["yellow", "green"]
  }

  assert {
    condition = toset([for t in aws_glue_crawler.raw.s3_target : t.path]) == toset([
      "s3://nyc-lake-test-lake/raw/yellow/",
      "s3://nyc-lake-test-lake/raw/green/",
    ])
    error_message = "raw crawler must target raw/<taxi>/ for each taxi type"
  }

  assert {
    condition     = keys(aws_glue_crawler.warehouse) == ["green", "yellow"]
    error_message = "one warehouse crawler per taxi type"
  }

  assert {
    condition     = aws_glue_crawler.warehouse["green"].table_prefix == "green_"
    error_message = "warehouse tables must be prefixed with the taxi type"
  }

  assert {
    condition = alltrue([
      for t in aws_glue_crawler.clean.s3_target : contains(t.exclusions, "_runs/**")
    ])
    error_message = "run summaries must not be crawled as tables"
  }
}

run "crawlers_never_rewrite_schemas" {
  command = plan

  assert {
    condition = alltrue([
      for c in concat([aws_glue_crawler.raw, aws_glue_crawler.clean], values(aws_glue_crawler.warehouse)) :
      one(c.schema_change_policy).update_behavior == "LOG" && one(c.schema_change_policy).delete_behavior == "LOG"
    ])
    error_message = "crawlers must log schema changes, not apply them"
  }
}

run "crawler_role_is_read_only_on_s3" {
  command = plan

  assert {
    condition = alltrue([
      for s in data.aws_iam_policy_document.crawler.statement :
      alltrue([for a in s.actions : !startswith(a, "s3:") || contains(["s3:GetObject", "s3:ListBucket"], a)])
    ])
    error_message = "the crawler role must not write to S3"
  }

  assert {
    condition = alltrue([
      for s in data.aws_iam_policy_document.crawler.statement : alltrue([for r in s.resources : r != "*"])
    ])
    error_message = "no wildcard resources"
  }
}

run "athena_workgroup_enforces_limits" {
  command = plan

  assert {
    condition     = one(aws_athena_workgroup.this.configuration).enforce_workgroup_configuration
    error_message = "the workgroup must enforce its settings"
  }

  assert {
    condition     = one(aws_athena_workgroup.this.configuration).bytes_scanned_cutoff_per_query == 10737418240
    error_message = "default scan cutoff must be 10 GiB"
  }

  assert {
    condition     = one(one(aws_athena_workgroup.this.configuration).result_configuration).output_location == "s3://nyc-lake-test-athena-results/results/"
    error_message = "results must go to the results bucket"
  }
}
