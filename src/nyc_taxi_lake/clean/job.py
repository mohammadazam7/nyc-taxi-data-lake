"""Clean one month of raw trips into the clean and quarantine zones.

Layout (mirrors the S3 layout used in AWS)::

    clean/yellow/pickup_date=2024-01-15/part-*.parquet
    quarantine/yellow/year=2024/month=01/part-*.parquet
    clean/_runs/yellow/2024-01.json        # row counts for the run

The clean zone is partitioned by pickup date because that is what every downstream
query filters on. Writes use dynamic partition overwrite, so re-running a month replaces
only that month's dates and the job is safe to retry.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field

from pyspark.sql import Column, DataFrame, SparkSession
from pyspark.sql import functions as F

from nyc_taxi_lake.clean.rules import tag_rejects
from nyc_taxi_lake.config import Settings
from nyc_taxi_lake.ingest.raw_zone import partition_dir
from nyc_taxi_lake.months import Month
from nyc_taxi_lake.paths import LakePath

log = logging.getLogger(__name__)

MONEY = "decimal(10,2)"

_AMOUNTS = {
    "fare_amount": "fare_amount",
    "extra": "extra_amount",
    "mta_tax": "mta_tax",
    "tip_amount": "tip_amount",
    "tolls_amount": "tolls_amount",
    "improvement_surcharge": "improvement_surcharge",
    "congestion_surcharge": "congestion_surcharge",
    "airport_fee": "airport_fee",
    "total_amount": "total_amount",
}


def _clean_columns() -> list[Column]:
    flag = F.upper(F.trim(F.col("store_and_fwd_flag")))
    return [
        F.col("trip_id"),
        F.col("VendorID").cast("int").alias("vendor_id"),
        F.col("tpep_pickup_datetime").cast("timestamp_ntz").alias("pickup_at"),
        F.col("tpep_dropoff_datetime").cast("timestamp_ntz").alias("dropoff_at"),
        F.col("passenger_count").cast("int").alias("passenger_count"),
        F.col("trip_distance").alias("trip_distance_mi"),
        F.col("RatecodeID").cast("int").alias("rate_code_id"),
        F.when(flag == "Y", True).when(flag == "N", False).alias("store_and_forward"),
        F.col("PULocationID").cast("int").alias("pickup_zone_id"),
        F.col("DOLocationID").cast("int").alias("dropoff_zone_id"),
        F.col("payment_type").cast("int").alias("payment_type_id"),
        *[F.col(src).cast(MONEY).alias(dst) for src, dst in _AMOUNTS.items()],
        F.to_date("tpep_pickup_datetime").alias("pickup_date"),
    ]


def standardise(tagged: DataFrame) -> DataFrame:
    """Snake-case names, integer IDs, a boolean flag and exact decimal money columns."""
    return tagged.select(*_clean_columns())


def split(raw: DataFrame, month: Month) -> tuple[DataFrame, DataFrame, DataFrame]:
    """Return ``(tagged, clean, quarantine)`` for one raw month."""
    tagged = tag_rejects(raw, month)
    clean = standardise(tagged.filter(F.col("reject_reason").isNull()))
    quarantine = tagged.filter(F.col("reject_reason").isNotNull()).withColumn(
        "source_month", F.lit(month.key)
    )
    return tagged, clean, quarantine


@dataclass(frozen=True)
class CleanSummary:
    month: str
    rows_in: int
    rows_clean: int
    rows_rejected: int
    rejected_by_reason: dict[str, int] = field(default_factory=dict)


def clean_month(spark: SparkSession, settings: Settings, month: Month) -> CleanSummary:
    raw_dir = partition_dir(settings.raw_root, settings.taxi_type, month)
    if not raw_dir.exists():
        raise FileNotFoundError(f"no raw partition for {month.key} at {raw_dir}; ingest it first")

    raw = spark.read.parquet(str(raw_dir))
    tagged, clean, quarantine = split(raw, month)
    tagged.persist()
    try:
        clean.write.mode("overwrite").partitionBy("pickup_date").parquet(
            str(settings.clean_root / settings.taxi_type)
        )
        quarantine.write.mode("overwrite").parquet(
            str(settings.quarantine_root / settings.taxi_type / month.partition)
        )
        counts = {
            row["reject_reason"]: row["count"]
            for row in tagged.groupBy("reject_reason").count().collect()
        }
    finally:
        tagged.unpersist()

    rows_clean = counts.pop(None, 0)
    summary = CleanSummary(
        month=month.key,
        rows_in=rows_clean + sum(counts.values()),
        rows_clean=rows_clean,
        rows_rejected=sum(counts.values()),
        rejected_by_reason=dict(sorted(counts.items())),
    )
    _write_summary(settings.clean_root / "_runs" / settings.taxi_type, summary)
    log.info(
        "cleaned %s: %d in, %d clean, %d quarantined",
        month.key,
        summary.rows_in,
        summary.rows_clean,
        summary.rows_rejected,
    )
    return summary


def _write_summary(directory: LakePath, summary: CleanSummary) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{summary.month}.json").write_text(json.dumps(asdict(summary), indent=2))
