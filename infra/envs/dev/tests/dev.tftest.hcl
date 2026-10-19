# Plan-only test of the wired-up environment with a mocked provider. It checks that the
# modules are connected to each other, not what each module builds; that is covered by
# the modules' own tests.

mock_provider "aws" {
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/nyc-lake-test-role" }
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
