"""Command-line entry point: ``nyc-lake <command>``."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

import pyarrow.parquet as pq

from nyc_taxi_lake.config import Settings
from nyc_taxi_lake.ingest.raw_zone import IngestResult, write_partition
from nyc_taxi_lake.ingest.sample import generate_month
from nyc_taxi_lake.ingest.tlc import download_month, trip_file_url
from nyc_taxi_lake.months import month_range


def _ingest(args: argparse.Namespace, settings: Settings) -> list[IngestResult]:
    results = []
    for month in month_range(args.start, args.end or args.start):
        if args.sample:
            table = generate_month(month, rows=args.sample_rows)
            source = f"synthetic://{settings.taxi_type}/{month.key}?rows={args.sample_rows}"
        else:
            path = download_month(settings, month, settings.lake_root / "_downloads")
            table = pq.read_table(path)
            source = trip_file_url(settings, month)
        results.append(
            write_partition(table, settings.raw_root, settings.taxi_type, month, source, args.force)
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
    return 2


if __name__ == "__main__":
    sys.exit(main())
