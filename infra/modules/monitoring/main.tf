# Alerting for the pipeline: one SNS topic that every failure signal publishes to.
#
# * Glue job runs that end FAILED, TIMEOUT or ERROR are matched by an EventBridge rule.
#   The event arrives within seconds of the run ending, so no alarm period is needed.
# * Spark tasks that fail and are retried do not fail the run. A CloudWatch alarm on
#   the jobs' numFailedTasks metric surfaces them before they turn into a failed run.
# * The quality job publishes its own breach summaries to the topic (milestone 4).
#
# The topic is not encrypted with the AWS managed SNS key, because EventBridge and
# CloudWatch cannot use that key to publish. Set kms_key_arn to a customer managed key
# whose policy allows both services if the alerts must be encrypted at rest.

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition
}

resource "aws_sns_topic" "alerts" {
  name              = "${var.name_prefix}-alerts"
  kms_master_key_id = var.kms_key_arn
  tags              = var.tags
}

data "aws_iam_policy_document" "alerts" {
  statement {
    sid       = "AccountOwnerManages"
    actions   = ["sns:*"]
    resources = [aws_sns_topic.alerts.arn]
    principals {
      type        = "AWS"
      identifiers = ["arn:${local.partition}:iam::${local.account_id}:root"]
    }
  }

  statement {
    sid       = "AlarmsAndEventsPublish"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com", "cloudwatch.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_sns_topic_policy" "alerts" {
  arn    = aws_sns_topic.alerts.arn
  policy = data.aws_iam_policy_document.alerts.json
}

resource "aws_sns_topic_subscription" "email" {
  for_each = var.alert_emails

  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = each.value
}

resource "aws_cloudwatch_event_rule" "glue_job_failed" {
  name        = "${var.name_prefix}-glue-job-failed"
  description = "A pipeline Glue job run ended without succeeding."
  tags        = var.tags

  event_pattern = jsonencode({
    source      = ["aws.glue"]
    detail-type = ["Glue Job State Change"]
    detail = {
      jobName = var.glue_job_names
      state   = ["FAILED", "TIMEOUT", "ERROR"]
    }
  })
}

resource "aws_cloudwatch_event_target" "glue_job_failed" {
  rule = aws_cloudwatch_event_rule.glue_job_failed.name
  arn  = aws_sns_topic.alerts.arn

  input_transformer {
    input_paths = {
      job   = "$.detail.jobName"
      run   = "$.detail.jobRunId"
      state = "$.detail.state"
      error = "$.detail.message"
    }
    input_template = "\"Glue job <job> run <run> ended <state>: <error>\""
  }
}

resource "aws_cloudwatch_metric_alarm" "glue_failed_tasks" {
  for_each = toset(var.glue_job_names)

  alarm_name        = "${each.value}-failed-tasks"
  alarm_description = "Spark tasks failed in ${each.value}. The run may still succeed on retries; check the job's logs."
  namespace         = "Glue"
  metric_name       = "glue.driver.aggregate.numFailedTasks"
  dimensions = {
    JobName  = each.value
    JobRunId = "ALL"
    Type     = "count"
  }

  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.failed_task_threshold
  # No runs means no data points; that is the normal state between monthly runs.
  treat_missing_data = "notBreaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
  tags          = var.tags
}
