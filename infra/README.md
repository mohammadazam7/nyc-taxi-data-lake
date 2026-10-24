# Infrastructure

Terraform for running the lake in AWS. Reusable modules live in `modules/`; `envs/dev`
is a root configuration that wires them together.

| Module | What it creates |
|---|---|
| `storage` | Lake, artifacts and Athena-results buckets: private, encrypted, TLS-only. Raw is versioned and moves to Glacier Instant Retrieval after 90 days; quarantine and query results expire. |
| `catalog` | A Glue database per zone (raw, clean, warehouse), crawlers that register new partitions, an Athena workgroup with a per-query scan limit, and the crawler role. |
| `jobs` | Glue 5.0 Spark jobs for the clean, model, quality and (given a workgroup) load stages, the entry script, and one IAM role per stage. |
| `warehouse` | Redshift Serverless namespace and workgroup (private, enhanced VPC routing), a daily RPU-hour usage limit, and the role `COPY` runs as, which can read only the warehouse zone. The admin password is generated and held in Secrets Manager by Redshift. |
| `monitoring` | The alert SNS topic and its email subscriptions, an EventBridge rule for failed Glue runs, and a failed-Spark-task CloudWatch alarm per job. |
| `orchestration` | A Step Functions state machine that runs the Glue jobs in order and waits for each, an EventBridge Scheduler monthly schedule (off by default), an alert rule for failed executions, and the two roles they run as. |

Each stage's role can read only the zones it consumes and write only the zones it
produces. No job can write the raw zone, and the quality job can only write its reports.

## Deploying the dev environment

You need Terraform 1.6+, AWS credentials, and an S3 bucket and DynamoDB table for
Terraform state.

```bash
cd infra/envs/dev
cp backend.hcl.example backend.hcl     # point at your state bucket
cp example.tfvars dev.tfvars           # pick a globally unique name_prefix
terraform init -backend-config=backend.hcl
terraform apply -var-file=dev.tfvars
```

The jobs install the package from a wheel in the artifacts bucket, so build and upload
it before the first run. From the repository root (the key must match `package_version`):

```bash
pip wheel . --no-deps -w dist
aws s3 cp dist/nyc_taxi_lake-0.1.0-py3-none-any.whl \
  "s3://$(terraform -chdir=infra/envs/dev output -raw artifacts_bucket)/wheels/"
```

## Running a month

Ingest needs a local filesystem, so land the raw data with the CLI (or the Docker
image) and sync it up. The model stage also needs TLC's `taxi_zone_lookup.csv`; put it
in `lake/raw/reference/` first and the sync copies it with the trips:

```bash
LAKE=$(terraform -chdir=infra/envs/dev output -raw lake_root)
nyc-lake ingest 2024-01
aws s3 sync lake/raw "$LAKE/raw"
```

Create the warehouse tables once from `sql/redshift/star_schema.sql` in the Redshift
query editor. The load job connects through the Data API as its IAM role, which
Redshift maps to the database user `"IAMR:<name_prefix>-glue-load"`. That user needs
`USAGE` on the `taxi` schema and `SELECT`, `INSERT` and `DELETE` on its tables, since a
load deletes the month's facts and the dimensions before copying them in again.

Then start the state machine, which runs clean, model, quality and load in order and
stops at the first failed run:

```bash
aws stepfunctions start-execution \
  --state-machine-arn "$(terraform -chdir=infra/envs/dev output -raw state_machine_arn)" \
  --input '{"start":"2024-01","end":"2024-01"}'
```

Each stage can still be started on its own with
`aws glue start-job-run --job-name <name_prefix>-<stage> --arguments '{"--start":"2024-01"}'`,
and `nyc-lake load` still runs from a workstation with `NYC_LAKE_REDSHIFT_WORKGROUP`
set. After a run, start the crawlers in the order `terraform output crawlers` lists
them to query the zones from the Athena workgroup.

## Monthly schedule

`schedule_enabled = true` turns on an EventBridge Scheduler schedule that starts the
state machine at 06:00 UTC on the 5th of each month with an empty input. The state
machine then processes the month two months earlier, since TLC publishes a month's
trips roughly two months after it ends. The raw month must already be in S3; the
schedule does not run ingest.

The workgroup has a daily limit of `max_rpu_hours_per_day` (4 by default); past it,
queries are refused rather than billed. Set it to `null` to remove the limit.

## Tests

Every module and environment has plan-only tests that use a mocked AWS provider, so they
need no credentials:

```bash
terraform -chdir=infra/modules/jobs init -backend=false
terraform -chdir=infra/modules/jobs test
```

CI runs `terraform fmt -check`, `validate` and `test` for each module and environment.
These tests check how resources are configured and connected. Nothing in this repository
has been applied to a real AWS account yet; the first real deployment is part of
milestone 9.
