# 0001. One codebase and CLI for local runs and AWS Glue

**Status:** Accepted

## Context

Glue jobs are slow to iterate on: a run takes minutes to start and costs money, and the
Glue console is a poor debugger. Pipelines that keep their transformation logic in Glue
scripts tend to be tested only in AWS, if at all.

## Decision

All transformation logic lives in the `nyc_taxi_lake` package and is exposed as `nyc-lake`
subcommands. Glue jobs install the package as a wheel and call the same commands through
a thin entry point (`glue_entry.py`). Lake locations are a `LakePath`, implemented by
`pathlib.Path` locally and by an S3 path class in AWS, chosen by whether `NYC_LAKE_ROOT`
starts with `s3://`.

## Consequences

- Every stage runs and is tested on a laptop and in CI with local Spark, without an AWS
  account.
- The Glue job definitions are configuration only; a change to behaviour is a reviewed
  code change with tests.
- The package must stay compatible with the Python and Spark versions of the Glue
  runtime (Glue 5.0: Python 3.11, Spark 3.5), which bounds the dependency versions.
- Stages that rely on local filesystem semantics (ingest's atomic rename) cannot run in
  Glue unchanged; ingest therefore runs outside AWS for now.
