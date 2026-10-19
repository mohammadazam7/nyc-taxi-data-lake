# Roadmap

The lake is built in milestones. Each one ships working, tested code on `main` and is
tagged when it completes. Checked items are done.

- [x] **M1 · Ingest.** Package layout, month partitioning, TLC downloader with retries,
      schema conformance across TLC file versions, idempotent raw-zone writer with
      manifests, synthetic data generator, CLI, CI.
- [x] **M2 · Clean.** PySpark job that deduplicates trips, drops impossible records
      (negative fares, dropoff before pickup, trips outside the file's month, unknown
      zones), standardises types and writes the clean zone partitioned by pickup date.
      Rejected rows go to a quarantine table with a reason code.
- [x] **M3 · Model.** Star schema: `fact_trips` plus `dim_date`, `dim_zone`,
      `dim_payment_type`, `dim_vendor`, `dim_rate_code`. Surrogate keys, SCD-1 dims,
      PySpark build job and SQL DDL for Redshift.
- [x] **M4 · Data quality.** Declarative checks (row counts vs. source, null rates,
      ranges, referential integrity, freshness) producing a JSON report per run, with a
      pluggable alert sink (log locally, SNS in AWS).
- [x] **M5 · AWS lake (Terraform).** S3 buckets for raw/clean/warehouse zones with
      lifecycle rules, Glue Data Catalog, crawlers and Glue job definitions wrapping the
      M2/M3 jobs, Athena workgroup, IAM least-privilege roles.
- [ ] **M6 · Warehouse load (Terraform).** Redshift Serverless namespace/workgroup,
      `COPY` loader from the warehouse zone, CloudWatch alarms and SNS topic for job
      failures and data-quality breaches.
- [ ] **M7 · Orchestration.** Glue workflow (or Step Functions) chaining ingest → clean →
      model → quality → load, monthly schedule, backfill command, Docker dev image.
- [ ] **M8 · Analytics.** SQL for trip volume, revenue and busiest zones; a small static
      dashboard generated from the warehouse; architecture docs and decision records.
- [ ] **M9 · v1.0.** Measured run on real TLC months (row counts, runtimes, costs),
      CHANGELOG, release.
