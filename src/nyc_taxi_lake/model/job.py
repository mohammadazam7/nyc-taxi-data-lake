"""Build the star schema in the warehouse zone from the clean zone.

Layout::

    warehouse/yellow/fact_trips/pickup_date=2024-01-15/part-*.parquet
    warehouse/yellow/dim_zone/part-*.parquet          # and the other dimensions
    warehouse/_runs/yellow/2024-01.json               # row counts for the run

Facts are rebuilt one month at a time with dynamic partition overwrite, like the clean
stage, so a month can be re-run on its own. The dimensions are small (a few hundred rows
at most, a few thousand for ``dim_date``) and are rewritten in full on every run, which
is what SCD type 1 needs anyway.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from nyc_taxi_lake.config import Settings
from nyc_taxi_lake.ingest.zone_lookup import LOOKUP_FILE
from nyc_taxi_lake.model.dimensions import dim_date, dim_payment_type, dim_rate_code, dim_vendor
from nyc_taxi_lake.model.facts import fact_trips
from nyc_taxi_lake.model.zones import dim_zone
from nyc_taxi_lake.months import Month

log = logging.getLogger(__name__)

# dim_date covers every TLC year that has Parquet files plus headroom, so a backfill or a
# new month never needs the calendar extended.
DATE_DIM_FIRST = date(2009, 1, 1)
DATE_DIM_LAST = date(2035, 12, 31)


def zone_lookup_path(settings: Settings) -> Path:
    """Where the TLC zone lookup lives in the raw zone."""
    return settings.raw_root / "reference" / LOOKUP_FILE


@dataclass(frozen=True)
class ModelSummary:
    month: str
    fact_rows: int
    dim_rows: dict[str, int]


def build_dimensions(spark: SparkSession, lookup_csv: Path) -> dict[str, DataFrame]:
    return {
        "dim_date": dim_date(spark, DATE_DIM_FIRST, DATE_DIM_LAST),
        "dim_zone": dim_zone(spark, lookup_csv),
        "dim_vendor": dim_vendor(spark),
        "dim_rate_code": dim_rate_code(spark),
        "dim_payment_type": dim_payment_type(spark),
    }


def read_clean_month(spark: SparkSession, settings: Settings, month: Month) -> DataFrame:
    clean_dir = settings.clean_root / settings.taxi_type
    if not clean_dir.exists():
        raise FileNotFoundError(f"no clean zone at {clean_dir}; run `nyc-lake clean` first")
    first = date(month.year, month.month, 1)
    nxt = month.next()
    # Filtering on the partition column prunes the read to this month's directories.
    return spark.read.parquet(str(clean_dir)).filter(
        (F.col("pickup_date") >= F.lit(first))
        & (F.col("pickup_date") < F.lit(date(nxt.year, nxt.month, 1)))
    )


def model_month(
    spark: SparkSession, settings: Settings, month: Month, lookup_csv: Path | None = None
) -> ModelSummary:
    lookup = lookup_csv or zone_lookup_path(settings)
    if not lookup.exists():
        raise FileNotFoundError(f"no zone lookup at {lookup}; land {LOOKUP_FILE} there first")

    out = settings.warehouse_root / settings.taxi_type
    dim_rows: dict[str, int] = {}
    for name, frame in build_dimensions(spark, lookup).items():
        frame = frame.cache()
        frame.write.mode("overwrite").parquet(str(out / name))
        dim_rows[name] = frame.count()
        frame.unpersist()

    facts = fact_trips(read_clean_month(spark, settings, month)).cache()
    try:
        facts.write.mode("overwrite").partitionBy("pickup_date").parquet(str(out / "fact_trips"))
        fact_rows = facts.count()
    finally:
        facts.unpersist()

    summary = ModelSummary(month=month.key, fact_rows=fact_rows, dim_rows=dim_rows)
    runs = settings.warehouse_root / "_runs" / settings.taxi_type
    runs.mkdir(parents=True, exist_ok=True)
    (runs / f"{month.key}.json").write_text(json.dumps(asdict(summary), indent=2))
    log.info("modelled %s: %d fact rows", month.key, fact_rows)
    return summary
