# Measured run

This page records end-to-end runs of `nyc-lake run` with their row counts and stage
durations, and the machine they ran on. Every number here was measured; the raw
timing reports are in [`runs/`](runs/).

## Scope

The runs below use the synthetic generator (`--sample`), not TLC data. The TLC CDN was
not reachable from the environment the runs were made in, so no figure on this page
describes real TLC months. The generator corrupts 2% of rows with one of five defects
(negative amounts, dropoff before pickup, pickup outside the file's month, unknown
zone, null passenger count; all but the last are rejected) and appends 0.5% exact
duplicates, so the clean and quarantine paths do real work. [Reproducing on TLC data](#reproducing-on-tlc-data) gives the
command for a real-data run.

## Environment

| | |
|---|---|
| CPU | 2 vCPU, Intel Xeon @ 2.80 GHz (cloud VM) |
| Memory | 7 GiB |
| Spark | PySpark 4.2.0, `local[*]` (one executor, 2 cores) |
| Java | OpenJDK 21 |
| Python | 3.13 |
| Storage | local disk, Parquet |

## Command

```bash
NYC_LAKE_ROOT=./lake nyc-lake run 2024-01 2024-03 --sample --sample-zones \
    --sample-rows 200000 --timings runs/synthetic-200k.json
```

`--sample-rows` sets the generated rows per month before defects are injected; the
generator adds 0.5% duplicates on top.

## Results

Three months (2024-01 to 2024-03), stages `ingest`, `clean`, `model` and `quality`.
Each Spark stage starts one session for the whole range.

### Row counts

| Rows per month | Raw rows | Clean rows | Quarantined | `fact_trips` rows | Quality |
|---:|---:|---:|---:|---:|---|
| 50,000 | 150,750 | 147,550 | 3,200 (2.1%) | 147,550 | pass, 3 of 3 months |
| 200,000 | 603,000 | 590,530 | 12,470 (2.1%) | 590,530 | pass, 3 of 3 months |

`fact_trips` matches the clean zone row for row in both runs, which is the
row-count-vs-source check the quality stage enforces.

### Stage durations (wall clock, seconds)

| Rows per month | ingest | clean | model | quality | Total |
|---:|---:|---:|---:|---:|---:|
| 50,000 | 1.7 | 37.1 | 26.9 | 30.2 | 96.0 |
| 200,000 | 7.0 | 45.0 | 30.2 | 35.3 | 117.4 |

## Analysis

- Fixed cost dominates at this scale. Quadrupling the input (452,250 more raw rows)
  added 21.4 s, or 22%, to the total. Most of the 96 s baseline is JVM and Spark
  session start-up, which each Spark stage pays once, plus per-job scheduling.
- `ingest` is the only stage that scales close to linearly (1.7 s to 7.0 s, 4.1x),
  because row generation runs in Python, not Spark.
- `clean` is the most expensive Spark stage: it deduplicates with a `row_number()`
  window over `trip_id` and writes two outputs (clean and quarantine).

## Limitations

- Synthetic data. Real TLC months are 3 to 4 million rows each with a different value
  distribution and file layout per vintage; the durations above do not extrapolate to
  them.
- Two cores and local disk. Glue workers, S3 I/O and Redshift `COPY` are not exercised,
  so the `load` stage and AWS costs are not measured here.
- One run per configuration. Durations on a shared cloud VM vary between runs; treat
  differences under a few seconds as noise.

## Reproducing on TLC data

With network access to the TLC CDN, drop `--sample` and use the real zone lookup:

```bash
NYC_LAKE_ROOT=./lake nyc-lake run 2024-01 2024-03 --timings runs/tlc-2024q1.json
```

Record the machine and the resulting JSON alongside the tables above.
