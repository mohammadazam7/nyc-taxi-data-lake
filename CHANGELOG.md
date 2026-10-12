# Changelog

All notable changes are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Milestone 2: PySpark clean stage (`nyc-lake clean`). Deduplicates on a content-hash
  `trip_id`, applies eight validation rules with stable reason codes, writes the clean
  zone partitioned by `pickup_date` with snake-case names and `decimal(10,2)` money, and
  sends rejected rows to a quarantine zone with their reason. Per-month run summaries
  under `clean/_runs/`. Spark tests run in their own CI job on Java 17.
- Milestone 1: package scaffold, `nyc-lake ingest` CLI, TLC downloader with retries and
  atomic writes, schema conformance across TLC file versions, idempotent raw-zone writer
  with per-partition manifests, synthetic data generator, CI on Python 3.11–3.13.
