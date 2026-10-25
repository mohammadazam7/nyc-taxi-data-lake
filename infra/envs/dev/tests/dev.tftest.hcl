# Plan-only test of the wired-up environment with a mocked provider. It checks that the
# modules are connected to each other, not what each module builds; that is covered by
# the modules' own tests.

mock_provider "aws" {
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/nyc-lake-test-role" }
  }
  mock_resource "aws_sfn_state_machine" {
    defaults = { arn = "arn:aws:states:us-east-1:123456789012:stateMachine:nyc-lake-test-pipeline" }
  }
  mock_resource "aws_cloudwatch_log_group" {
    defaults = { arn = "arn:aws:logs:us-east-1:123456789012:log-group:/aws/vendedlogs/states/nyc-lake-test-pipeline" }
  }
  mock_resource "aws_sns_topic" {
    defaults = { arn = "arn:aws:sns:us-east-1:123456789012:nyc-lake-test-alerts" }
  }
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
  mock_data "aws_region" {
    defaults = { name = "us-east-1" }
  }
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
}

variables {
  name_prefix     = "nyc-lake-test"
  package_version = "0.1.0"
}

run "jobs_run_against_the_lake_bucket" {
  command = plan

  assert {
    condition     = output.lake_root == "s3://nyc-lake-test-lake"
    error_message = "lake_root must point at the storage module's lake bucket"
  }

  assert {
    condition     = module.jobs.job_names.clean == "nyc-lake-test-clean"
    error_message = "jobs must be named after the environment prefix"
  }
}

run "wheel_key_follows_the_package_version" {
  command = plan

  variables {
    package_version = "1.0.0"
  }

  assert {
    condition     = output.package_wheel_key == "wheels/nyc_taxi_lake-1.0.0-py3-none-any.whl"
    error_message = "wheel key must be built from package_version"
  }
}

run "catalog_has_a_database_per_zone" {
  command = plan

  assert {
    condition     = output.glue_databases == { raw = "nyc_lake_test_raw", clean = "nyc_lake_test_clean", warehouse = "nyc_lake_test_warehouse" }
    error_message = "expected raw, clean and warehouse databases named after the prefix"
  }
}

run "every_job_is_monitored" {
  command = plan

  assert {
    condition     = module.monitoring.glue_failure_rule == "nyc-lake-test-glue-job-failed"
    error_message = "the environment must route Glue job failures to the alert topic"
  }

  assert {
    condition     = length(module.monitoring.alarm_names) == 4
    error_message = "every Glue job must have a failed-task alarm"
  }
}

run "load_job_targets_the_warehouse" {
  command = plan

  assert {
    condition     = module.jobs.job_names.load == "nyc-lake-test-load"
    error_message = "the environment must create a load job"
  }
}

run "state_machine_runs_every_job" {
  command = plan

  assert {
    condition     = module.orchestration.stages == ["clean", "model", "quality", "load"]
    error_message = "the state machine must run every stage, ending with the load"
  }

  assert {
    condition     = module.orchestration.state_machine_name == "nyc-lake-test-pipeline"
    error_message = "the state machine must be named after the prefix"
  }
}

run "warehouse_is_named_after_the_prefix" {
  command = plan

  assert {
    condition     = output.redshift_workgroup == "nyc-lake-test-warehouse" && output.redshift_database == "taxi"
    error_message = "the loader's workgroup and database must come from the warehouse module"
  }
}
