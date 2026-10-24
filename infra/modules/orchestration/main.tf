# Runs the pipeline's AWS stages in order as one Step Functions execution:
#
#   ResolveMonth, ResolveRange, Clean, Model, Quality, Load (if the jobs module has a
#   load job), Done
#
# Each stage is a Glue job started with the .sync integration, so the execution waits
# for the run to end and fails as soon as one does. Quality exits non-zero on an error
# finding, so a month that fails its checks is never loaded into Redshift.
#
# An execution processes the month range in its input:
#
#   aws stepfunctions start-execution --state-machine-arn <arn> \
#     --input '{"start":"2024-01","end":"2024-03"}'
#
# With no "start", it processes the single month lag_months before the execution's start
# time. That is the case for the scheduled run, whose input is empty: the run on
# 2026-11-05 processes 2026-09.
#
# Ingest is not a stage here. It needs a local filesystem (see the CLI's require_local),
# so it runs in the Docker image and syncs the raw zone to S3 before an execution starts.

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition
  region     = data.aws_region.current.name

  stages = [for s in ["clean", "model", "quality", "load"] : s if contains(keys(var.job_names), s)]

  # JSONata: the month lag_months before the execution's start time, as YYYY-MM.
  # Months are counted from year 0 so that subtracting the lag crosses year boundaries.
  default_month = join("; ", [
    "($t := $states.context.Execution.StartTime",
    "$i := $number($substring($t, 0, 4)) * 12 + $number($substring($t, 5, 2)) - 1 - ${var.lag_months}",
    "$string($floor($i / 12)) & '-' & $pad($string($i % 12 + 1), -2, '0'))",
  ])

  stage_states = {
    for i, s in local.stages : title(s) => {
      Type     = "Task"
      Comment  = "Run the ${s} Glue job over the range and wait for it to end."
      Resource = "arn:${local.partition}:states:::glue:startJobRun.sync"
      Arguments = {
        JobName = var.job_names[s]
        Arguments = {
          "--start" = "{% $start %}"
          "--end"   = "{% $end %}"
        }
      }
      Next = i < length(local.stages) - 1 ? title(local.stages[i + 1]) : "Done"
    }
  }

  definition = {
    Comment       = "NYC taxi lake: clean, model, check and load a range of months."
    QueryLanguage = "JSONata"
    StartAt       = "ResolveMonth"
    States = merge(
      {
        ResolveMonth = {
          Type    = "Pass"
          Comment = "The default month, used when the input names no range."
          Assign  = { month = "{% ${local.default_month} %}" }
          Next    = "ResolveRange"
        }
        ResolveRange = {
          Type    = "Pass"
          Comment = "start and end from the input; end defaults to start."
          Assign = {
            start = "{% $exists($states.input.start) ? $states.input.start : $month %}"
            end   = "{% $exists($states.input.end) ? $states.input.end : ($exists($states.input.start) ? $states.input.start : $month) %}"
          }
          Next = title(local.stages[0])
        }
        Done = {
          Type = "Succeed"
        }
      },
      local.stage_states,
    )
  }
}

resource "aws_cloudwatch_log_group" "pipeline" {
  # The /aws/vendedlogs/ prefix keeps Step Functions from adding a statement per log
  # group to the account's CloudWatch Logs resource policy, which has a size limit.
  name              = "/aws/vendedlogs/states/${var.name_prefix}-pipeline"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_sfn_state_machine" "pipeline" {
  name       = "${var.name_prefix}-pipeline"
  role_arn   = aws_iam_role.state_machine.arn
  type       = "STANDARD"
  definition = jsonencode(local.definition)
  tags       = var.tags

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.pipeline.arn}:*"
    level                  = "ERROR"
    include_execution_data = false
  }
}

resource "aws_scheduler_schedule" "monthly" {
  name        = "${var.name_prefix}-monthly"
  description = "Process the month ${var.lag_months} months before each run."
  state       = var.schedule_enabled ? "ENABLED" : "DISABLED"

  schedule_expression          = var.schedule_expression
  schedule_expression_timezone = "UTC"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sfn_state_machine.pipeline.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({})
  }
}

# The monitoring module already alerts on each failed Glue run. This rule adds one
# alert per failed execution, which also covers failures outside a Glue run (a stopped
# execution, a missing job, an IAM error). When a Glue run fails both alerts arrive;
# the execution's input holds the month range to re-run.
resource "aws_cloudwatch_event_rule" "execution_failed" {
  name        = "${var.name_prefix}-pipeline-failed"
  description = "A pipeline execution ended without succeeding."
  tags        = var.tags

  event_pattern = jsonencode({
    source      = ["aws.states"]
    detail-type = ["Step Functions Execution Status Change"]
    detail = {
      stateMachineArn = [aws_sfn_state_machine.pipeline.arn]
      status          = ["FAILED", "TIMED_OUT", "ABORTED"]
    }
  })
}

resource "aws_cloudwatch_event_target" "execution_failed" {
  rule = aws_cloudwatch_event_rule.execution_failed.name
  arn  = var.alert_topic_arn

  input_transformer {
    input_paths = {
      execution = "$.detail.name"
      status    = "$.detail.status"
    }
    input_template = "\"Pipeline execution <execution> ended <status>. Its input names the month range; the failed state names the stage.\""
  }
}
