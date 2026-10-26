# 0005. Portable analytics SQL and a static dashboard

**Status:** Accepted

## Context

The analytics queries need to run in two places: against the warehouse zone with Spark,
for local development and CI, and against Redshift, for users with SQL clients. The
results need a presentation that a reviewer can open without credentials, a BI tool
licence or a running server.

## Decision

Each query is a `.sql` file written in the subset of SQL that Spark SQL, Redshift and
Athena share: unqualified table names, resolved by temporary views in Spark and by
`search_path` in Redshift, and named parameters `:start_key` and `:end_key` that both
Spark and the Redshift Data API bind, so no value is formatted into SQL text. Filters
use `pickup_date_key`, which exists in both stores, rather than the Spark-only
`pickup_date` partition column.

`nyc-lake analytics` writes every result to one JSON report. `nyc-lake dashboard`
renders the report as one HTML file with inline SVG charts and no scripts or external
requests. The page states its data source from the raw-zone manifests and labels
synthetic data.

## Consequences

- One query text is tested in CI and runs unchanged in Redshift; a test checks that the
  queries agree with each other and with direct sums over the fact table.
- Features specific to one engine are unavailable. Date parts come from `dim_date`
  attributes rather than engine-specific date functions.
- The dashboard is static: there is no filtering or drill-down, and a new range needs
  a new report. That is acceptable for a monthly batch pipeline and keeps the page
  usable as a CI artifact.
- Rendering depends only on the JSON report, so a Redshift-backed runner can produce the
  same dashboard without changes to the renderer.
