# Plan-only tests with a mocked provider: they need no AWS credentials.
#
# The copy role's ARN is mocked during plan (override_during, Terraform 1.9+) so the
# namespace's default role can be compared with it; otherwise both are unknown.

mock_provider "aws" {
  mock_resource "aws_iam_role" {
    override_during = plan
    defaults        = { arn = "arn:aws:iam::123456789012:role/nyc-lake-test-redshift-copy" }
  }
  mock_resource "aws_redshiftserverless_workgroup" {
    defaults = { arn = "arn:aws:redshift-serverless:us-east-1:123456789012:workgroup/abc" }
  }
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
}

variables {
  name_prefix = "nyc-lake-test"
  lake_bucket = "nyc-lake-test-lake"
}

run "workgroup_is_private_and_small" {
  command = plan

  assert {
    condition     = aws_redshiftserverless_workgroup.this.base_capacity == 8
    error_message = "default capacity must be the 8 RPU minimum"
  }

  assert {
    condition     = !aws_redshiftserverless_workgroup.this.publicly_accessible
    error_message = "the workgroup must not be publicly accessible"
  }

  assert {
    condition     = aws_redshiftserverless_workgroup.this.enhanced_vpc_routing
    error_message = "COPY traffic must stay in the VPC"
  }
}

run "password_is_managed_by_redshift" {
  command = plan

  assert {
    condition     = aws_redshiftserverless_namespace.this.manage_admin_password
    error_message = "the admin password must live in Secrets Manager, not in state"
  }

  assert {
    condition     = aws_redshiftserverless_namespace.this.admin_user_password == null
    error_message = "no password may be passed in"
  }
}

run "daily_limit_deactivates_the_workgroup" {
  command = plan

  assert {
    condition     = aws_redshiftserverless_usage_limit.daily[0].amount == 4 && aws_redshiftserverless_usage_limit.daily[0].breach_action == "deactivate"
    error_message = "a breached daily limit must stop queries, not just log"
  }
}

run "limit_can_be_turned_off" {
  command = plan

  variables {
    max_rpu_hours_per_day = null
  }

  assert {
    condition     = length(aws_redshiftserverless_usage_limit.daily) == 0
    error_message = "a null limit must create no usage limit"
  }
}

run "copy_role_reads_only_the_warehouse_zone" {
  command = plan

  variables {
    taxi_types = ["yellow", "green"]
  }

  assert {
    condition = toset(flatten([
      for s in data.aws_iam_policy_document.copy.statement : s.resources if contains(s.actions, "s3:GetObject")
      ])) == toset([
      "arn:aws:s3:::nyc-lake-test-lake/warehouse/yellow/*",
      "arn:aws:s3:::nyc-lake-test-lake/warehouse/green/*",
    ])
    error_message = "COPY may read warehouse/<taxi>/ and nothing else"
  }

  assert {
    condition = alltrue([
      for s in data.aws_iam_policy_document.copy.statement :
      alltrue([for a in s.actions : contains(["s3:GetObject", "s3:ListBucket"], a)])
    ])
    error_message = "the copy role must be read-only"
  }

  assert {
    condition     = aws_redshiftserverless_namespace.this.default_iam_role_arn == aws_iam_role.copy.arn
    error_message = "COPY ... IAM_ROLE default must resolve to the copy role"
  }
}

run "capacity_must_be_a_multiple_of_8" {
  command = plan

  variables {
    base_capacity_rpu = 12
  }

  expect_failures = [var.base_capacity_rpu]
}
