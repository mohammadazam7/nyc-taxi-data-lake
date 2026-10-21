# Plan-only tests with a mocked provider: they need no AWS credentials.

mock_provider "aws" {
  mock_resource "aws_sns_topic" {
    defaults = { arn = "arn:aws:sns:us-east-1:123456789012:nyc-lake-test-alerts" }
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
  name_prefix    = "nyc-lake-test"
  glue_job_names = ["nyc-lake-test-clean", "nyc-lake-test-model", "nyc-lake-test-quality"]
}

run "failed_runs_of_every_job_reach_the_topic" {
  command = plan

  assert {
    condition     = toset(jsondecode(aws_cloudwatch_event_rule.glue_job_failed.event_pattern).detail.jobName) == toset(var.glue_job_names)
    error_message = "the rule must match every pipeline job"
  }

  assert {
    condition     = toset(jsondecode(aws_cloudwatch_event_rule.glue_job_failed.event_pattern).detail.state) == toset(["FAILED", "TIMEOUT", "ERROR"])
    error_message = "the rule must match every unsuccessful end state, and not SUCCEEDED or STOPPED"
  }
}

run "one_failed_task_alarm_per_job" {
  command = plan

  assert {
    condition     = toset(keys(aws_cloudwatch_metric_alarm.glue_failed_tasks)) == toset(var.glue_job_names)
    error_message = "expected one alarm per job"
  }

  assert {
    condition     = alltrue([for a in aws_cloudwatch_metric_alarm.glue_failed_tasks : a.treat_missing_data == "notBreaching" && a.threshold == 0])
    error_message = "idle periods must not alarm, and the first failed task must"
  }

  assert {
    condition     = alltrue([for a in aws_cloudwatch_metric_alarm.glue_failed_tasks : a.dimensions.JobRunId == "ALL"])
    error_message = "alarms must aggregate over all runs of a job"
  }
}

run "no_subscriptions_by_default" {
  command = plan

  assert {
    condition     = length(aws_sns_topic_subscription.email) == 0
    error_message = "no one is subscribed unless alert_emails is set"
  }
}

run "subscribes_each_address" {
  command = plan

  variables {
    alert_emails = ["data-oncall@example.com", "analytics@example.com"]
  }

  assert {
    condition     = length(aws_sns_topic_subscription.email) == 2 && alltrue([for s in aws_sns_topic_subscription.email : s.protocol == "email"])
    error_message = "each address gets an email subscription"
  }
}

run "rejects_an_empty_job_list" {
  command = plan

  variables {
    glue_job_names = []
  }

  expect_failures = [var.glue_job_names]
}
