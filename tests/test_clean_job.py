from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import pyarrow.parquet as pq
import pytest

from nyc_taxi_lake.config import Settings
from nyc_taxi_lake.ingest.raw_zone import write_partition
from nyc_taxi_lake.ingest.sample import generate_month
from nyc_taxi_lake.months import Month

if TYPE_CHECKING:
    from pyspark.sql import SparkSession

pytestmark = pytest.mark.spark

JAN = Month(2024, 1)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        lake_root=tmp_path,
        tlc_base_url="https://example.test/trip-data",
        taxi_type="yellow",
        http_timeout_s=5,
        http_retries=1,
    )


@pytest.fixture
def landed(settings: Settings) -> int:
    table = generate_month(JAN, rows=3_000)
    write_partition(table, settings.raw_root, "yellow", JAN, "synthetic://test")
    return table.num_rows


def test_every_row_ends_up_clean_or_quarantined(
    spark: SparkSession, settings: Settings, landed: int
) -> None:
    from nyc_taxi_lake.clean.job import clean_month

    summary = clean_month(spark, settings, JAN)

    assert summary.rows_in == landed
    assert summary.rows_clean + summary.rows_rejected == landed
    assert summary.rows_rejected > 0
    assert summary.rejected_by_reason["DUPLICATE"] == landed - 3_000

    clean = spark.read.parquet(str(settings.clean_root / "yellow"))
    quarantine = spark.read.parquet(str(settings.quarantine_root / "yellow" / JAN.partition))
    assert clean.count() == summary.rows_clean
    assert quarantine.count() == summary.rows_rejected
    assert clean.select("trip_id").distinct().count() == summary.rows_clean


def test_clean_zone_is_partitioned_by_pickup_date_within_the_month(
    spark: SparkSession, settings: Settings, landed: int
) -> None:
    from nyc_taxi_lake.clean.job import clean_month

    clean_month(spark, settings, JAN)
    dates = sorted(p.name for p in (settings.clean_root / "yellow").glob("pickup_date=*"))
    assert dates[0] == "pickup_date=2024-01-01"
    assert dates[-1] == "pickup_date=2024-01-31"


def test_clean_rows_have_standard_types(
    spark: SparkSession, settings: Settings, landed: int
) -> None:
    from nyc_taxi_lake.clean.job import clean_month

    clean_month(spark, settings, JAN)
    clean = spark.read.parquet(str(settings.clean_root / "yellow"))
    types = dict(clean.dtypes)
    assert types["pickup_at"] == "timestamp_ntz"
    assert types["passenger_count"] == "int"
    assert types["store_and_forward"] == "boolean"
    assert types["fare_amount"] == "decimal(10,2)"
    assert types["pickup_date"] == "date"

    row = clean.orderBy("trip_id").first()
    assert row is not None
    assert isinstance(row["total_amount"], Decimal)
    assert row["fare_amount"] >= 0


def test_quarantine_keeps_raw_columns_and_reason(
    spark: SparkSession, settings: Settings, landed: int
) -> None:
    from nyc_taxi_lake.clean.job import clean_month

    clean_month(spark, settings, JAN)
    table = pq.read_table(settings.quarantine_root / "yellow" / JAN.partition)
    assert {"tpep_pickup_datetime", "fare_amount", "reject_reason", "source_month"} <= set(
        table.column_names
    )
    assert set(table.column("source_month").to_pylist()) == {"2024-01"}
    assert None not in table.column("reject_reason").to_pylist()


def test_rerun_is_idempotent(spark: SparkSession, settings: Settings, landed: int) -> None:
    from nyc_taxi_lake.clean.job import clean_month

    first = clean_month(spark, settings, JAN)
    second = clean_month(spark, settings, JAN)

    assert first == second
    assert spark.read.parquet(str(settings.clean_root / "yellow")).count() == first.rows_clean
    saved = json.loads((settings.clean_root / "_runs" / "yellow" / "2024-01.json").read_text())
    assert saved["rows_clean"] == first.rows_clean


def test_missing_raw_partition_is_a_clear_error(spark: SparkSession, settings: Settings) -> None:
    from nyc_taxi_lake.clean.job import clean_month

    with pytest.raises(FileNotFoundError, match="ingest it first"):
        clean_month(spark, settings, JAN)
