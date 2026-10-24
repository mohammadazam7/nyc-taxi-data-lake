# Plan-only tests with a mocked provider: they need no AWS credentials. The state
# machine's definition is built from variables, so it is known at plan time and the
# tests check it directly.

mock_provider "aws" {
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/nyc-lake-test-pipeline" }
  }
  mock_resource "aws_cloudwatch_log_group" {
    defaults = { arn = "arn:aws:logs:us-east-1:123456789012:log-group:/aws/vendedlogs/states/nyc-lake-test-pipeline" }
  }
  mock_resource "aws_sfn_state_machine" {
    defaults = { arn = "arn:aws:states:us-east-1:123456789012:stateMachine:nyc-lake-test-pipeline" }
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
  alert_topic_arn = "arn:aws:sns:us-east-1:123456789012:nyc-lake-test-alerts"
  job_names = {
    clean   = "nyc-lake-test-clean"
    model   = "nyc-lake-test-model"
    quality = "nyc-lake-test-quality"
    load    = "nyc-lake-test-load"
  }
}

run "stages_run_in_pipeline_order" {
  command = plan

  assert {
    condition     = output.stages == ["clean", "model", "quality", "load"]
    error_message = "stages must run clean, model, quality, load"
  }

  assert {
    condition     = jsondecode(aws_sfn_state_machine.pipeline.definition).StartAt == "ResolveMonth"
    error_message = "the execution must resolve its month range first"
  }

  assert {
    condition     = jsondecode(aws_sfn_state_machine.pipeline.definition).States.ResolveRange.Next == "Clean"
    error_message = "the first stage after the range is clean"
  }

  assert {
    condition = [
      for s in ["Clean", "Model", "Quality", "Load"] : jsondecode(aws_sfn_state_machine.pipeline.definition).States[s].Next
    ] == ["Model", "Quality", "Load", "Done"]
    error_message = "each stage must lead to the next, and load to Done"
  }

  assert {
    condition     = jsondecode(aws_sfn_state_machine.pipeline.definition).States.Done.Type == "Succeed"
    error_message = "the last state must succeed"
  }
}

run "stages_wait_for_their_glue_runs" {
  command = plan

  assert {
    condition = alltrue([
      for s in ["Clean", "Model", "Quality", "Load"] :
      jsondecode(aws_sfn_state_machine.pipeline.definition).States[s].Resource == "arn:aws:states:::glue:startJobRun.sync"
    ])
    error_message = "every stage must use the .sync integration so a failed run fails the execution"
  }

  assert {
    condition     = jsondecode(aws_sfn_state_machine.pipeline.definition).States.Quality.Arguments.JobName == "nyc-lake-test-quality"
    error_message = "each stage must start its own job"
  }

  assert {
    condition     = jsondecode(aws_sfn_state_machine.pipeline.definition).States.Model.Arguments.Arguments == { "--start" = "{% $start %}", "--end" = "{% $end %}" }
    error_message = "each run must receive the resolved month range"
  }

  assert {
    condition     = jsondecode(aws_sfn_state_machine.pipeline.definition).QueryLanguage == "JSONata"
    error_message = "the definition's expressions are JSONata"
  }
}

run "without_a_load_job_quality_is_last" {
  command = plan

  variables {
    job_names = {
      clean   = "nyc-lake-test-clean"
      model   = "nyc-lake-test-model"
      quality = "nyc-lake-test-quality"
    }
  }

  assert {
    condition     = jsondecode(aws_sfn_state_machine.pipeline.definition).States.Quality.Next == "Done"
    error_message = "quality must be the last stage when there is no load job"
  }

  assert {
    condition     = !contains(keys(jsondecode(aws_sfn_state_machine.pipeline.definition).States), "Load")
    error_message = "there must be no load state without a load job"
  }
}

run "default_month_honours_the_lag" {
  command = plan

  variables {
    lag_months = 3
  }

  assert {
    condition     = strcontains(jsondecode(aws_sfn_state_machine.pipeline.definition).States.ResolveMonth.Assign.month, "- 1 - 3;")
    error_message = "the default month must be lag_months before the execution starts"
  }
}

run "schedule_is_off_until_enabled" {
  command = plan

  assert {
    condition     = aws_scheduler_schedule.monthly.state == "DISABLED"
    error_message = "the schedule must be disabled by default"
  }

  assert {
    condition     = aws_scheduler_schedule.monthly.schedule_expression == "cron(0 6 5 * ? *)" && aws_scheduler_schedule.monthly.schedule_expression_timezone == "UTC"
    error_message = "the default schedule is 06:00 UTC on the 5th of each month"
  }

  assert {
    condition     = jsondecode(aws_scheduler_schedule.monthly.target[0].input) == {}
    error_message = "the scheduled run must pass no range, so the state machine picks the month"
  }
}

run "schedule_can_be_enabled" {
  command = plan

  variables {
    schedule_enabled = true
  }

  assert {
    condition     = aws_scheduler_schedule.monthly.state == "ENABLED"
    error_message = "schedule_enabled must turn the schedule on"
  }
}

# The rule's pattern embeds the state machine's ARN, which is unknown at plan time, so
# the statuses are checked through the local the pattern is built from.
run "failed_executions_reach_the_topic" {
  command = plan

  assert {
    condition     = toset(local.failed_statuses) == toset(["FAILED", "TIMED_OUT", "ABORTED"])
    error_message = "the rule must match every unsuccessful end state"
  }

  assert {
    condition     = aws_cloudwatch_event_target.execution_failed.arn == var.alert_topic_arn
    error_message = "failed executions must publish to the alert topic"
  }
}

run "execution_logs_go_to_a_vended_log_group" {
  command = plan

  assert {
    condition     = aws_cloudwatch_log_group.pipeline.name == "/aws/vendedlogs/states/nyc-lake-test-pipeline"
    error_message = "the log group must use the /aws/vendedlogs/ prefix"
  }

  assert {
    condition     = aws_sfn_state_machine.pipeline.logging_configuration[0].level == "ERROR" && !aws_sfn_state_machine.pipeline.logging_configuration[0].include_execution_data
    error_message = "the state machine must log errors without execution data"
  }
}

run "missing_core_stage_is_rejected" {
  command = plan

  variables {
    job_names = {
      clean = "nyc-lake-test-clean"
      model = "nyc-lake-test-model"
    }
  }

  expect_failures = [var.job_names]
}
