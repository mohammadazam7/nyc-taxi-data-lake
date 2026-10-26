# 0004. Step Functions rather than Glue workflows or Airflow

**Status:** Accepted

## Context

The AWS stages need to run in order once a month, stop on the first failure, gate the
load on the quality result, alert on failure, and accept a month range for backfills.
The candidates were Glue workflows, Amazon MWAA (managed Airflow) and Step Functions.

## Decision

A Step Functions standard state machine runs the clean, model, quality and load Glue
jobs with the `startJobRun.sync` integration. An EventBridge Scheduler schedule starts
it monthly with an empty input, and the state machine derives the target month from the
execution start time with a JSONata expression. Failed, timed-out and aborted executions
publish to the alert SNS topic. Locally, `nyc-lake run` and `nyc-lake backfill` provide
the same ordering.

## Consequences

- No always-on scheduler: Step Functions bills per state transition, a few cents a year
  at this cadence, while the smallest MWAA environment bills by the hour.
- Glue workflows were rejected because a month range has to be set as workflow run
  properties through the API and read by each job, and failure notification needs a
  separate EventBridge rule. Step Functions takes the range as execution input and
  expresses the quality gate and the failure notification in the definition itself.
- The month calculation lives in the state machine, so there is no scheduler state to
  keep in step with the data; a manual execution passes an explicit range.
- Ingest is not a state machine step (see ADR 0001), so a fully unattended monthly run
  needs ingest to move into AWS.
