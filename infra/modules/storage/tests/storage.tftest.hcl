# Plan-only tests with a mocked provider: they need no AWS credentials.
#   terraform test   (or: tofu test)

mock_provider "aws" {}

variables {
  name_prefix = "nyc-lake-test"
}

run "creates_three_private_buckets" {
  command = plan

  assert {
    condition = toset([for b in aws_s3_bucket.this : b.bucket]) == toset([
      "nyc-lake-test-lake",
      "nyc-lake-test-artifacts",
      "nyc-lake-test-athena-results",
    ])
    error_message = "unexpected bucket names"
  }

  assert {
    condition = alltrue([
      for b in aws_s3_bucket_public_access_block.this :
      b.block_public_acls && b.block_public_policy && b.ignore_public_acls && b.restrict_public_buckets
    ])
    error_message = "every bucket must block public access"
  }

  assert {
    condition     = length(aws_s3_bucket_policy.tls_only) == 3
    error_message = "every bucket needs the TLS-only policy"
  }

  assert {
    condition     = alltrue([for b in aws_s3_bucket.this : !b.force_destroy])
    error_message = "buckets must not be force-destroyable by default"
  }
}

run "only_the_lake_is_versioned" {
  command = plan

  assert {
    condition     = aws_s3_bucket_versioning.lake.versioning_configuration[0].status == "Enabled"
    error_message = "the lake bucket must be versioned"
  }
}

run "lake_lifecycle_rules_follow_the_zones" {
  command = plan

  variables {
    raw_glacier_days       = 60
    quarantine_expiry_days = 90
  }

  assert {
    condition = toset([for r in aws_s3_bucket_lifecycle_configuration.lake.rule : r.id]) == toset([
      "raw-tiering",
      "quarantine-expiry",
      "clean-noncurrent",
      "warehouse-noncurrent",
      "quality-noncurrent",
      "abort-incomplete-uploads",
    ])
    error_message = "unexpected lifecycle rules"
  }

  assert {
    condition = one([
      for r in aws_s3_bucket_lifecycle_configuration.lake.rule : one(r.transition).days
      if r.id == "raw-tiering"
    ]) == 60
    error_message = "raw tiering must use raw_glacier_days"
  }

  assert {
    condition = one([
      for r in aws_s3_bucket_lifecycle_configuration.lake.rule : one(r.expiration).days
      if r.id == "quarantine-expiry"
    ]) == 90
    error_message = "quarantine expiry must use quarantine_expiry_days"
  }
}

run "rejects_invalid_prefix" {
  command = plan

  variables {
    name_prefix = "NYC_Lake"
  }

  expect_failures = [var.name_prefix]
}

run "bucket_names_are_known_at_plan" {
  command = plan

  assert {
    condition     = output.lake_root == "s3://nyc-lake-test-lake" && output.artifacts_bucket == "nyc-lake-test-artifacts"
    error_message = "bucket outputs must be known before apply"
  }
}
