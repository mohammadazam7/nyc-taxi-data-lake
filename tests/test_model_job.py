from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from nyc_taxi_lake.config import Settings
from nyc_taxi_lake.ingest.raw_zone import write_partition
from nyc_taxi_lake.ingest.sample import generate_month
from nyc_taxi_lake.ingest.zone_lookup import write_sample_lookup
from nyc_taxi_lake.months import Month

if TYPE_CHECKING:
    from pyspark.sql import SparkSession

pytestmark = pytest.mark.spark

JAN, FEB = Month(2024, 1), Month(2024, 2)


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
def cleaned(spark: SparkSession, settings: Settings) -> dict[str, int]:
    """Two clean months and a placeholder zone lookup; returns clean rows per month."""
    from nyc_taxi_lake.clean.job import clean_month
    from nyc_taxi_lake.model.job import zone_lookup_path

    rows = {}
    for month in (JAN, FEB):
        write_partition(generate_month(month, rows=1_500), settings.raw_root, "yellow", month, "t")
        rows[month.key] = clean_month(spark, settings, month).rows_clean
    write_sample_lookup(zone_lookup_path(settings))
    return rows


def test_one_fact_row_per_clean_trip_and_month_is_isolated(
    spark: SparkSession, settings: Settings, cleaned: dict[str, int]
) -> None:
    from nyc_taxi_lake.model.job import model_month

    summary = model_month(spark, settings, JAN)
    assert summary.fact_rows == cleaned["2024-01"]

    facts = spark.read.parquet(str(settings.warehouse_root / "yellow" / "fact_trips"))
    assert facts.count() == cleaned["2024-01"]
    assert facts.filter("pickup_date >= '2024-02-01'").count() == 0

    model_month(spark, settings, FEB)
    facts = spark.read.parquet(str(settings.warehouse_root / "yellow" / "fact_trips"))
    assert facts.count() == cleaned["2024-01"] + cleaned["2024-02"]


def test_rerunning_a_month_replaces_it(
    spark: SparkSession, settings: Settings, cleaned: dict[str, int]
) -> None:
    from nyc_taxi_lake.model.job import model_month

    model_month(spark, settings, JAN)
    model_month(spark, settings, FEB)
    model_month(spark, settings, JAN)

    facts = spark.read.parquet(str(settings.warehouse_root / "yellow" / "fact_trips"))
    assert facts.count() == sum(cleaned.values())
    assert facts.select("trip_id").distinct().count() == facts.count()


def test_writes_dimensions_and_a_run_summary(
    spark: SparkSession, settings: Settings, cleaned: dict[str, int]
) -> None:
    from nyc_taxi_lake.model.job import model_month

    summary = model_month(spark, settings, JAN)

    out = settings.warehouse_root / "yellow"
    for name, count in summary.dim_rows.items():
        assert spark.read.parquet(str(out / name)).count() == count
    assert summary.dim_rows["dim_zone"] == 266  # 265 zones + unknown
    saved = json.loads((settings.warehouse_root / "_runs" / "yellow" / "2024-01.json").read_text())
    assert saved["fact_rows"] == summary.fact_rows


def test_missing_inputs_fail_with_a_hint(spark: SparkSession, settings: Settings) -> None:
    from nyc_taxi_lake.model.job import model_month, zone_lookup_path

    with pytest.raises(FileNotFoundError, match="zone lookup"):
        model_month(spark, settings, JAN)
    write_sample_lookup(zone_lookup_path(settings))
    with pytest.raises(FileNotFoundError, match="nyc-lake clean"):
        model_month(spark, settings, JAN)
