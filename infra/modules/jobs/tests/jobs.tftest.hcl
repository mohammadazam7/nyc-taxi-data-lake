# Plan-only tests with a mocked provider: they need no AWS credentials. Policy
# documents are mocked, so the role scoping is checked through the prefix locals the
# statements are built from.

mock_provider "aws" {
  # Glue validates role_arn, so the mocked roles need a well-formed ARN.
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/nyc-lake-test-glue" }
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
  name_prefix       = "nyc-lake-test"
  lake_bucket       = "nyc-lake-test-lake"
  artifacts_bucket  = "nyc-lake-test-artifacts"
  package_wheel_key = "wheels/nyc_taxi_lake-0.5.0-py3-none-any.whl"
}

run "one_job_per_stage" {
  command = plan

  assert {
    condition     = toset([for j in aws_glue_job.stage : j.name]) == toset(["nyc-lake-test-clean", "nyc-lake-test-model", "nyc-lake-test-quality"])
    error_message = "expected clean, model and quality jobs"
  }

  assert {
    condition     = alltrue([for k, j in aws_glue_job.stage : j.default_arguments["--stage"] == k])
    error_message = "each job must run its own stage"
  }

  assert {
    condition     = alltrue([for j in aws_glue_job.stage : j.execution_property[0].max_concurrent_runs == 1])
    error_message = "a stage must not run twice at once"
  }

  assert {
    condition     = alltrue([for j in aws_glue_job.stage : j.timeout == 60 && j.glue_version == "5.0"])
    error_message = "jobs must use Glue 5.0 and a one-hour timeout by default"
  }
}

run "jobs_install_the_package_wheel" {
  command = plan

  assert {
    condition     = alltrue([for j in aws_glue_job.stage : j.default_arguments["--additional-python-modules"] == "s3://nyc-lake-test-artifacts/wheels/nyc_taxi_lake-0.5.0-py3-none-any.whl"])
    error_message = "every job must install the wheel"
  }

  assert {
    condition     = alltrue([for j in aws_glue_job.stage : j.command[0].script_location == "s3://nyc-lake-test-artifacts/glue/nyc_lake_job.py"])
    error_message = "every job must run the shared entry script"
  }

  assert {
    condition     = alltrue([for j in aws_glue_job.stage : j.default_arguments["--lake-root"] == "s3://nyc-lake-test-lake"])
    error_message = "lake root must be the lake bucket"
  }
}

run "each_stage_has_its_own_role" {
  command = plan

  assert {
    condition     = length(distinct([for r in aws_iam_role.stage : r.name])) == 3
    error_message = "expected one role per stage"
  }

  assert {
    condition     = toset(local.write_prefixes.clean) == toset(["clean/yellow/", "clean/_runs/yellow/", "quarantine/yellow/"])
    error_message = "clean writes the clean and quarantine zones only"
  }

  assert {
    condition     = toset(local.write_prefixes.model) == toset(["warehouse/yellow/", "warehouse/_runs/yellow/"])
    error_message = "model writes the warehouse zone only"
  }

  assert {
    condition     = toset(local.write_prefixes.quality) == toset(["quality/yellow/"])
    error_message = "quality writes its reports only"
  }

  assert {
    condition     = alltrue([for stage, prefixes in local.write_prefixes : alltrue([for p in prefixes : !startswith(p, "raw/")])])
    error_message = "no job may write the raw zone"
  }
}

run "log_sink_without_a_topic" {
  command = plan

  assert {
    condition     = aws_glue_job.stage["quality"].default_arguments["--alert-sink"] == "log"
    error_message = "quality must log alerts when no topic is given"
  }

  assert {
    condition     = !contains(keys(aws_glue_job.stage["clean"].default_arguments), "--alert-sink")
    error_message = "only the quality job takes alert arguments"
  }
}

run "sns_sink_with_a_topic" {
  command = plan

  variables {
    alert_topic_arn = "arn:aws:sns:us-east-1:123456789012:nyc-lake-alerts"
  }

  assert {
    condition     = aws_glue_job.stage["quality"].default_arguments["--alert-sink"] == "sns"
    error_message = "quality must publish to SNS when a topic is given"
  }

  assert {
    condition     = aws_glue_job.stage["quality"].default_arguments["--sns-topic-arn"] == "arn:aws:sns:us-east-1:123456789012:nyc-lake-alerts"
    error_message = "quality must get the topic ARN"
  }
}

run "roles_cover_every_taxi_type" {
  command = plan

  variables {
    taxi_types = ["green", "yellow"]
  }

  assert {
    condition     = toset(local.read_prefixes.clean) == toset(["raw/green/", "raw/yellow/"])
    error_message = "clean must read every configured taxi type"
  }

  assert {
    condition     = aws_glue_job.stage["clean"].default_arguments["--taxi-type"] == "yellow"
    error_message = "yellow stays the default taxi type when it is configured"
  }
}

run "rejects_a_non_wheel_package" {
  command = plan

  variables {
    package_wheel_key = "wheels/nyc_taxi_lake.tar.gz"
  }

  expect_failures = [var.package_wheel_key]
}

run "rejects_too_few_workers" {
  command = plan

  variables {
    workers = { clean = 1, model = 4, quality = 2 }
  }

  expect_failures = [var.workers]
}

run "outputs_name_every_stage" {
  command = plan

  assert {
    condition     = output.job_names == { clean = "nyc-lake-test-clean", model = "nyc-lake-test-model", quality = "nyc-lake-test-quality" }
    error_message = "job_names must map each stage to its job"
  }
}

run "no_load_job_without_a_workgroup" {
  command = plan

  assert {
    condition     = !contains(keys(aws_glue_job.stage), "load")
    error_message = "the load job needs a workgroup"
  }
}

run "load_job_with_a_workgroup" {
  command = plan

  variables {
    load = {
      workgroup_name = "nyc-lake-test-warehouse"
      workgroup_arn  = "arn:aws:redshift-serverless:us-east-1:123456789012:workgroup/0000"
      database_name  = "taxi"
    }
  }

  assert {
    condition     = aws_glue_job.stage["load"].default_arguments["--redshift-workgroup"] == "nyc-lake-test-warehouse"
    error_message = "the load job must target the given workgroup"
  }

  assert {
    condition     = aws_glue_job.stage["load"].default_arguments["--redshift-database"] == "taxi"
    error_message = "the load job must target the given database"
  }

  assert {
    condition     = aws_glue_job.stage["load"].number_of_workers == 2
    error_message = "the load job only issues SQL and gets Glue's minimum of 2 workers"
  }

  assert {
    condition     = length(local.read_prefixes.load) == 0 && length(local.write_prefixes.load) == 0
    error_message = "the load job's role must not touch the lake; COPY reads it as the namespace role"
  }

  assert {
    condition     = !contains(keys(aws_glue_job.stage["clean"].default_arguments), "--redshift-workgroup")
    error_message = "only the load job takes Redshift arguments"
  }
}
