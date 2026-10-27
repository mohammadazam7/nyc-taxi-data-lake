"""Command-line entry point: ``nyc-lake <command>``."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import pyarrow.parquet as pq

from nyc_taxi_lake.config import Settings
from nyc_taxi_lake.ingest.raw_zone import IngestResult, write_partition
from nyc_taxi_lake.ingest.sample import generate_month
from nyc_taxi_lake.ingest.tlc import download_month, trip_file_url
from nyc_taxi_lake.months import month_range
from nyc_taxi_lake.paths import require_local
from nyc_taxi_lake.pipeline import (
    DEFAULT_STAGES,
    STAGES,
    RunOptions,
    backfill,
    parse_stages,
    run_stages,
    timings,
)


def _ingest(args: argparse.Namespace, settings: Settings) -> list[IngestResult]:
    # Ingest writes with pyarrow and local renames; in AWS the raw zone is synced up.
    lake = require_local(settings.lake_root, "ingest")
    results = []
    for month in month_range(args.start, args.end or args.start):
        if args.sample:
            table = generate_month(month, rows=args.sample_rows)
            source = f"synthetic://{settings.taxi_type}/{month.key}?rows={args.sample_rows}"
        else:
            path = download_month(settings, month, lake / "_downloads")
            table = pq.read_table(path)
            source = trip_file_url(settings, month)
        results.append(
            write_partition(table, lake / "raw", settings.taxi_type, month, source, args.force)
        )
    return results


def _clean(args: argparse.Namespace, settings: Settings) -> int:
    # Imported here so `nyc-lake ingest` works without the [spark] extra installed.
    from nyc_taxi_lake.clean.job import clean_month
    from nyc_taxi_lake.spark import get_spark

    spark = get_spark("nyc-lake-clean", master=args.master)
    try:
        for month in month_range(args.start, args.end or args.start):
            s = clean_month(spark, settings, month)
            reasons = ", ".join(f"{k}={v:,}" for k, v in s.rejected_by_reason.items()) or "-"
            print(
                f"{s.month}  {s.rows_in:>10,} in  {s.rows_clean:>10,} clean  "
                f"{s.rows_rejected:>8,} quarantined  ({reasons})"
            )
    finally:
        spark.stop()
    return 0


def _model(args: argparse.Namespace, settings: Settings) -> int:
    from nyc_taxi_lake.ingest.zone_lookup import write_sample_lookup
    from nyc_taxi_lake.model.job import model_month, zone_lookup_path
    from nyc_taxi_lake.spark import get_spark

    lookup = zone_lookup_path(settings)
    if args.sample_zones and not lookup.exists():
        write_sample_lookup(require_local(lookup, "--sample-zones"))
        print(f"wrote placeholder zone lookup to {lookup}")

    spark = get_spark("nyc-lake-model", master=args.master)
    try:
        for month in month_range(args.start, args.end or args.start):
            s = model_month(spark, settings, month)
            print(f"{s.month}  {s.fact_rows:>10,} fact rows  ({len(s.dim_rows)} dimensions)")
    finally:
        spark.stop()
    return 0


def _quality(args: argparse.Namespace, settings: Settings) -> int:
    from nyc_taxi_lake.quality.alerts import make_sink
    from nyc_taxi_lake.quality.job import check_month
    from nyc_taxi_lake.quality.report import Status
    from nyc_taxi_lake.quality.spec import load_suite
    from nyc_taxi_lake.spark import get_spark

    checks = load_suite(args.suite)
    sink = make_sink(args.alert_sink, args.sns_topic_arn)
    failing = {Status.FAIL} if args.fail_on == "error" else {Status.FAIL, Status.WARN}

    spark = get_spark("nyc-lake-quality", master=args.master)
    exit_code = 0
    try:
        for month in month_range(args.start, args.end or args.start):
            report = check_month(spark, settings, month, checks, sink)
            counts = report.to_dict()["counts"]
            print(
                f"{report.month}  {report.status.value:4}  {counts['pass']} passed  "
                f"{counts['warn']} warned  {counts['fail']} failed"
            )
            if report.status in failing:
                exit_code = 1
    finally:
        spark.stop()
    return exit_code


def _load(args: argparse.Namespace, settings: Settings) -> int:
    from nyc_taxi_lake.load.redshift import DataApiRunner
    from nyc_taxi_lake.load.statements import month_load

    warehouse = str(settings.warehouse_root / settings.taxi_type)
    months = month_range(args.start, args.end or args.start)
    if args.dry_run:
        for month in months:
            print(f"-- {month.key}")
            for sql in month_load(warehouse, month, schema=args.schema, iam_role=args.iam_role):
                print(f"{sql};")
        return 0

    if not args.workgroup:
        print("nyc-lake load: --workgroup or $NYC_LAKE_REDSHIFT_WORKGROUP is required")
        return 2
    runner = DataApiRunner(args.workgroup, args.database)
    for month in months:
        statements = month_load(warehouse, month, schema=args.schema, iam_role=args.iam_role)
        statement_id = runner.run(statements)
        print(f"{month.key}  loaded  {len(statements)} statements  {statement_id}")
    return 0


def _analytics(args: argparse.Namespace, settings: Settings) -> int:
    from nyc_taxi_lake.analytics.queries import load_queries, month_bounds
    from nyc_taxi_lake.analytics.results import AnalyticsReport
    from nyc_taxi_lake.analytics.spark_runner import register_warehouse, run_queries
    from nyc_taxi_lake.spark import get_spark

    months = month_range(args.start, args.end or args.start)
    start, end = months[0], months[-1]
    spark = get_spark("nyc-lake-analytics", master=args.master)
    try:
        register_warehouse(spark, settings.warehouse_root / settings.taxi_type)
        results = run_queries(spark, load_queries(), month_bounds(start, end))
    finally:
        spark.stop()

    report = AnalyticsReport(settings.taxi_type, start.key, end.key, tuple(results))
    out_dir = settings.analytics_root / settings.taxi_type
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{start.key}_{end.key}.json"
    out.write_text(report.to_json())
    for result in results:
        print(f"{result.name:22} {len(result.rows):>5} rows")
    print(f"wrote {out}")
    return 0


def _dashboard(args: argparse.Namespace, settings: Settings) -> int:
    from nyc_taxi_lake.analytics.dashboard import provenance_note, render
    from nyc_taxi_lake.analytics.results import AnalyticsReport
    from nyc_taxi_lake.ingest.raw_zone import MANIFEST, partition_dir

    months = month_range(args.start, args.end or args.start)
    name = f"{months[0].key}_{months[-1].key}"
    reports = settings.analytics_root / settings.taxi_type
    source = reports / f"{name}.json"
    if not source.exists():
        print(f"nyc-lake dashboard: no report at {source}; run nyc-lake analytics first")
        return 1
    report = AnalyticsReport.from_json(source.read_text())

    sources = []
    for month in months:
        manifest = partition_dir(settings.raw_root, settings.taxi_type, month) / MANIFEST
        if manifest.exists():
            sources.append(json.loads(manifest.read_text())["source"])
    note = args.note if args.note is not None else provenance_note(sources)

    out = reports / f"{name}.html"
    out.write_text(render(report, source_note=note))
    print(f"wrote {out}")
    return 0


def _run_options(args: argparse.Namespace) -> RunOptions:
    return RunOptions(
        master=args.master,
        sample=args.sample,
        sample_rows=args.sample_rows,
        sample_zones=args.sample_zones,
        load_dry_run=args.load_dry_run,
    )


def _run(args: argparse.Namespace) -> int:
    months = month_range(args.start, args.end or args.start)
    steps = run_stages(months, args.stages, _run_options(args), main)
    for step in steps:
        print(f"nyc-lake run: {step.stage:8} exit {step.exit_code}  {step.seconds:8.1f} s")
    print(f"nyc-lake run: total {sum(s.seconds for s in steps):.1f} s")
    if args.timings is not None:
        args.timings.parent.mkdir(parents=True, exist_ok=True)
        args.timings.write_text(json.dumps(timings(steps), indent=2) + "\n")
    failed = next((s for s in steps if not s.ok), None)
    if failed is not None:
        print(f"nyc-lake run: {failed.stage} failed for {failed.start}..{failed.end}")
        return failed.exit_code
    return 0


def _backfill(args: argparse.Namespace, settings: Settings) -> int:
    result = backfill(
        args.start,
        args.end,
        args.stages,
        _run_options(args),
        settings,
        main,
        force=args.force,
    )
    print(f"backfill: {len(result.done)} done, {len(result.skipped)} skipped (already passed)")
    if result.failed is not None:
        f = result.failed
        print(f"backfill: {f.stage} failed for {f.start}; re-run the same command to resume")
        return f.exit_code
    return 0


def _stages(value: str) -> tuple[str, ...]:
    try:
        return parse_stages(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _add_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--stages",
        type=_stages,
        default=DEFAULT_STAGES,
        help=f"comma-separated subset of {','.join(STAGES)} (default: {','.join(DEFAULT_STAGES)})",
    )
    parser.add_argument("--sample", action="store_true", help="ingest synthetic data")
    parser.add_argument("--sample-rows", type=int, default=50_000)
    parser.add_argument(
        "--sample-zones", action="store_true", help="model with a placeholder zone lookup"
    )
    parser.add_argument(
        "--load-dry-run", action="store_true", help="print the load SQL instead of running it"
    )
    parser.add_argument("--master", default="local[*]", help="Spark master URL")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nyc-lake", description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="land monthly trip files in the raw zone")
    ingest.add_argument("start", help="first month, YYYY-MM")
    ingest.add_argument("end", nargs="?", help="last month, YYYY-MM (default: start)")
    ingest.add_argument(
        "--sample",
        action="store_true",
        help="generate synthetic data instead of downloading from TLC",
    )
    ingest.add_argument("--sample-rows", type=int, default=50_000)
    ingest.add_argument("--force", action="store_true", help="rewrite even if unchanged")

    clean = sub.add_parser("clean", help="validate raw months into the clean and quarantine zones")
    clean.add_argument("start", help="first month, YYYY-MM")
    clean.add_argument("end", nargs="?", help="last month, YYYY-MM (default: start)")
    clean.add_argument(
        "--master",
        default="local[*]",
        help="Spark master URL (default: local[*]; ignored when submitted to a cluster)",
    )

    model = sub.add_parser("model", help="build fact_trips and the dimensions from clean months")
    model.add_argument("start", help="first month, YYYY-MM")
    model.add_argument("end", nargs="?", help="last month, YYYY-MM (default: start)")
    model.add_argument(
        "--sample-zones",
        action="store_true",
        help="write a placeholder zone lookup if the real one has not been landed",
    )
    model.add_argument("--master", default="local[*]", help="Spark master URL")

    quality = sub.add_parser("quality", help="run data-quality checks on modelled months")
    quality.add_argument("start", help="first month, YYYY-MM")
    quality.add_argument("end", nargs="?", help="last month, YYYY-MM (default: start)")
    quality.add_argument(
        "--suite", type=Path, help="TOML check suite (default: the suite shipped with the package)"
    )
    quality.add_argument(
        "--alert-sink",
        choices=["log", "sns"],
        default=os.environ.get("NYC_LAKE_ALERT_SINK", "log"),
        help="where breaches are sent (default: log, or $NYC_LAKE_ALERT_SINK)",
    )
    quality.add_argument(
        "--sns-topic-arn",
        default=os.environ.get("NYC_LAKE_SNS_TOPIC_ARN"),
        help="topic for the sns sink (default: $NYC_LAKE_SNS_TOPIC_ARN)",
    )
    quality.add_argument(
        "--fail-on",
        choices=["error", "warn"],
        default="error",
        help="exit non-zero on failed error checks only (default), or on warnings too",
    )
    quality.add_argument("--master", default="local[*]", help="Spark master URL")

    load = sub.add_parser("load", help="COPY modelled months into Redshift Serverless")
    load.add_argument("start", help="first month, YYYY-MM")
    load.add_argument("end", nargs="?", help="last month, YYYY-MM (default: start)")
    load.add_argument(
        "--workgroup",
        default=os.environ.get("NYC_LAKE_REDSHIFT_WORKGROUP"),
        help="Redshift Serverless workgroup (default: $NYC_LAKE_REDSHIFT_WORKGROUP)",
    )
    load.add_argument(
        "--database",
        default=os.environ.get("NYC_LAKE_REDSHIFT_DATABASE", "taxi"),
        help="database in the namespace (default: taxi, or $NYC_LAKE_REDSHIFT_DATABASE)",
    )
    load.add_argument("--schema", default="taxi", help="schema holding the star (default: taxi)")
    load.add_argument(
        "--iam-role",
        default="default",
        help="role ARN for COPY (default: the namespace's default role)",
    )
    load.add_argument("--dry-run", action="store_true", help="print the SQL instead of running it")

    analytics = sub.add_parser(
        "analytics", help="run the analytics queries over modelled months into a JSON report"
    )
    analytics.add_argument("start", help="first month, YYYY-MM")
    analytics.add_argument("end", nargs="?", help="last month, YYYY-MM (default: start)")
    analytics.add_argument("--master", default="local[*]", help="Spark master URL")

    dashboard = sub.add_parser(
        "dashboard", help="render an analytics report as a static HTML page next to it"
    )
    dashboard.add_argument("start", help="first month, YYYY-MM")
    dashboard.add_argument("end", nargs="?", help="last month, YYYY-MM (default: start)")
    dashboard.add_argument(
        "--note",
        help="text shown under the title (default: the data source, from the raw manifests)",
    )

    run = sub.add_parser("run", help="run the stages in order, each over the whole month range")
    run.add_argument("start", help="first month, YYYY-MM")
    run.add_argument("end", nargs="?", help="last month, YYYY-MM (default: start)")
    run.add_argument(
        "--timings", type=Path, help="write each stage's exit code and duration to this JSON file"
    )
    _add_run_arguments(run)

    back = sub.add_parser(
        "backfill",
        help="run every stage one month at a time, skipping months that already passed",
    )
    back.add_argument("start", help="first month, YYYY-MM")
    back.add_argument("end", help="last month, YYYY-MM")
    back.add_argument("--force", action="store_true", help="re-run months that already passed")
    _add_run_arguments(back)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = Settings.from_env()
    if args.command == "ingest":
        for r in _ingest(args, settings):
            status = "skipped" if r.skipped else "landed"
            print(f"{r.month}  {status:8}  {r.rows:>10,} rows  {r.path}")
        return 0
    if args.command == "clean":
        return _clean(args, settings)
    if args.command == "model":
        return _model(args, settings)
    if args.command == "quality":
        return _quality(args, settings)
    if args.command == "load":
        return _load(args, settings)
    if args.command == "analytics":
        return _analytics(args, settings)
    if args.command == "dashboard":
        return _dashboard(args, settings)
    if args.command == "run":
        return _run(args)
    if args.command == "backfill":
        return _backfill(args, settings)
    return 2


if __name__ == "__main__":
    sys.exit(main())
