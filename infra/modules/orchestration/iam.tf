# Two roles: the state machine's, which can start and stop only the pipeline's Glue
# jobs and deliver its logs, and the scheduler's, which can only start the state
# machine.

data "aws_iam_policy_document" "states_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "state_machine" {
  name               = "${var.name_prefix}-pipeline"
  assume_role_policy = data.aws_iam_policy_document.states_assume.json
  tags               = var.tags
}

data "aws_iam_policy_document" "state_machine" {
  # startJobRun.sync polls the run with GetJobRun and stops it with BatchStopJobRun
  # when the execution is stopped.
  statement {
    sid = "RunPipelineJobs"
    actions = [
      "glue:StartJobRun",
      "glue:GetJobRun",
      "glue:GetJobRuns",
      "glue:BatchStopJobRun",
    ]
    resources = [
      for s in local.stages : "arn:${local.partition}:glue:${local.region}:${local.account_id}:job/${var.job_names[s]}"
    ]
  }

  # Log delivery actions take no resource.
  statement {
    sid = "DeliverExecutionLogs"
    actions = [
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies",
      "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "state_machine" {
  name   = "run-pipeline"
  role   = aws_iam_role.state_machine.id
  policy = data.aws_iam_policy_document.state_machine.json
}

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${var.name_prefix}-pipeline-schedule"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
  tags               = var.tags
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    sid       = "StartPipeline"
    actions   = ["states:StartExecution"]
    resources = [aws_sfn_state_machine.pipeline.arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "start-pipeline"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}
