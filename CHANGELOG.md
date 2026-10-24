# Changelog

All notable changes are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Milestone 7: orchestration. `nyc-lake run` chains the stages over a month range,
  stage-major, and stops at the first failure; `nyc-lake backfill` runs month by month
  and skips months whose quality report passed, so it resumes after a failure. A
  development `Dockerfile` with PySpark and OpenJDK 17. The Glue entry point accepts
  `--stage load`, and the `jobs` module creates a load job when given a Redshift
  workgroup. New `orchestration` module: a Step Functions state machine that runs
  clean, model, quality and load with `startJobRun.sync`, derives the default month
  from the execution start time, reports failed executions to SNS, and is started
  monthly by a disabled-by-default EventBridge Scheduler schedule. CI builds the image
  and runs a synthetic month through it, and checks that a backfill resumes.
- Milestone 6: warehouse load and alerting. `warehouse` Terraform module with a Redshift
  Serverless namespace and workgroup, a daily RPU-hour usage limit and a `COPY` role
  scoped to the warehouse zone. `nyc-lake load` runs each month's dimension reloads and
  fact `DELETE`/`COPY` as one Redshift Data API transaction, with `--dry-run` to print
  the SQL. `monitoring` module with the alert SNS topic, an EventBridge rule for failed
  Glue runs and a failed-task CloudWatch alarm per job; the dev environment wires the
  quality job's alerts to it.
- Milestone 5: the lake in Terraform. `storage` module for the lake, artifacts and
  Athena-results buckets with encryption, TLS-only policies and lifecycle rules;
  `catalog` module with a Glue database per zone, crawlers and an Athena workgroup;
  `jobs` module running clean, model and quality as Glue 5.0 jobs through a shared
  entry script, each under an IAM role scoped to its input and output zones;
  `envs/dev` root configuration. `NYC_LAKE_ROOT` accepts an `s3://` URI for the
  Spark stages. Plan-only `terraform test` suites with a mocked
  provider, run in CI with `fmt` and `validate`.
- Milestone 4: data-quality checks (`nyc-lake quality`). A strict TOML suite with
  row-count reconciliation, quarantine rate, null rate, value range, referential
  integrity and month-completeness checks, each at `error` or `warn` severity. One JSON
  report per month under `quality/`, breaches sent to a log or SNS alert sink, non-zero
  exit on failure. The CI smoke run now checks quality after modelling.
- Milestone 3: star schema (`nyc-lake model`). Builds `fact_trips` (one row per clean
  trip, partitioned by `pickup_date`) and `dim_date`, `dim_zone`, `dim_vendor`,
  `dim_rate_code` and `dim_payment_type` in the warehouse zone. Hash surrogate keys so
  months rebuild independently, an unknown member in every dimension, SCD type 1.
  Redshift DDL in `sql/redshift/star_schema.sql`, checked against the job's output by a
  test. CI smoke run now includes the model stage.
- Milestone 2: PySpark clean stage (`nyc-lake clean`). Deduplicates on a content-hash
  `trip_id`, applies eight validation rules with stable reason codes, writes the clean
  zone partitioned by `pickup_date` with snake-case names and `decimal(10,2)` money, and
  sends rejected rows to a quarantine zone with their reason. Per-month run summaries
  under `clean/_runs/`. Spark tests run in their own CI job on Java 17.
- Milestone 1: package scaffold, `nyc-lake ingest` CLI, TLC downloader with retries and
  atomic writes, schema conformance across TLC file versions, idempotent raw-zone writer
  with per-partition manifests, synthetic data generator, CI on Python 3.11-3.13.

### Changed
- `envs/dev` replaces the `alert_topic_arn` variable with `alert_emails`; the topic is
  now created by the `monitoring` module.
