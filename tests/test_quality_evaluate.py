from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from nyc_taxi_lake.config import Settings
from nyc_taxi_lake.ingest.raw_zone import write_partition
from nyc_taxi_lake.ingest.sample import generate_month
from nyc_taxi_lake.ingest.zone_lookup import write_sample_lookup
from nyc_taxi_lake.months import Month
from nyc_taxi_lake.quality.spec import (
    Freshness,
    NullRate,
    QuarantineRate,
    ReferentialIntegrity,
    RowCountReconciles,
    ValueRange,
    load_suite,
)

if TYPE_CHECKING:
    from pyspark.sql import SparkSession

    from nyc_taxi_lake.quality.evaluate import MonthTables

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
def tables(spark: SparkSession, settings: Settings) -> MonthTables:
    """January ingested, cleaned and modelled from 2,000 synthetic rows."""
    from nyc_taxi_lake.clean.job import clean_month
    from nyc_taxi_lake.model.job import model_month, zone_lookup_path
    from nyc_taxi_lake.quality.evaluate import MonthTables

    write_partition(generate_month(JAN, rows=2_000), settings.raw_root, "yellow", JAN, "t")
    clean_month(spark, settings, JAN)
    write_sample_lookup(zone_lookup_path(settings))
    model_month(spark, settings, JAN)
    return MonthTables(spark, settings, JAN)


def test_default_suite_passes_on_a_healthy_month(tables: MonthTables) -> None:
    from nyc_taxi_lake.quality.evaluate import evaluate_suite

    results = evaluate_suite(load_suite(), tables)
    failed = [(r.name, r.detail) for r in results if not r.passed]
    assert failed == []


def test_row_counts_reconcile_and_quarantine_rate_is_measured(tables: MonthTables) -> None:
    from nyc_taxi_lake.quality.evaluate import evaluate_check

    raw = evaluate_check(RowCountReconciles("rc", "error", "raw", "clean"), tables)
    assert raw.passed and raw.observed == 0
    assert "quarantined" in raw.detail

    rate = evaluate_check(QuarantineRate("q", "error", 0.0), tables)
    assert not rate.passed  # the generator always injects some defects
    assert isinstance(rate.observed, float) and 0 < rate.observed < 0.1


def test_a_lost_partition_breaks_reconciliation(tables: MonthTables, settings: Settings) -> None:
    from nyc_taxi_lake.quality.evaluate import evaluate_check

    facts = settings.warehouse_root / "yellow" / "fact_trips"
    dropped = next(p for p in sorted(facts.iterdir()) if p.name.startswith("pickup_date="))
    for f in dropped.iterdir():
        f.unlink()
    dropped.rmdir()
    tables.release()

    result = evaluate_check(RowCountReconciles("rc", "error", "clean", "fact_trips"), tables)
    assert not result.passed
    assert isinstance(result.observed, int) and result.observed > 0


def test_null_rate_and_range_report_the_share_of_bad_rows(tables: MonthTables) -> None:
    from nyc_taxi_lake.quality.evaluate import evaluate_check

    nulls = evaluate_check(NullRate("n", "warn", "fact_trips", "passenger_count", 0.0), tables)
    assert not nulls.passed and nulls.status.value == "warn"
    assert isinstance(nulls.observed, float) and nulls.observed > 0

    strict = ValueRange("r", "error", "fact_trips", "trip_distance_mi", None, 1.0, 0.0)
    result = evaluate_check(strict, tables)
    assert not result.passed and result.status.value == "fail"
    assert "values outside" in result.detail


def test_orphan_keys_are_counted_and_sampled(
    tables: MonthTables, spark: SparkSession, settings: Settings
) -> None:
    from pyspark.sql import functions as F

    from nyc_taxi_lake.quality.evaluate import evaluate_check

    # Rewrite dim_zone without one busy zone, as a bad lookup file would.
    out = settings.warehouse_root / "yellow"
    zones = spark.read.parquet(str(out / "dim_zone")).filter(F.col("zone_id") != 161)
    zones.write.parquet(str(out / "dim_zone_partial"))
    shutil.rmtree(out / "dim_zone")
    (out / "dim_zone_partial").rename(out / "dim_zone")
    tables.release()

    check = ReferentialIntegrity(
        "ri", "error", "fact_trips", "pickup_zone_key", "dim_zone.zone_key"
    )
    result = evaluate_check(check, tables)
    assert not result.passed
    assert isinstance(result.observed, int) and result.observed > 0
    assert "e.g." in result.detail


def test_freshness_measures_the_gap_to_month_end(tables: MonthTables) -> None:
    from nyc_taxi_lake.quality.evaluate import evaluate_check

    loose = evaluate_check(Freshness("f", "error", "fact_trips", "pickup_at", 48), tables)
    assert loose.passed
    assert isinstance(loose.observed, float) and 0 <= loose.observed < 48
    tight = evaluate_check(Freshness("f", "error", "fact_trips", "pickup_at", 0), tables)
    assert not tight.passed


def test_missing_inputs_fail_the_check_instead_of_the_run(
    spark: SparkSession, settings: Settings
) -> None:
    from nyc_taxi_lake.quality.evaluate import MonthTables, evaluate_check

    empty = MonthTables(spark, settings, JAN)
    result = evaluate_check(NullRate("n", "error", "fact_trips", "trip_id", 0.0), empty)
    assert not result.passed
    assert "fact_trips not found" in result.detail


def test_unknown_column_fails_the_check(tables: MonthTables) -> None:
    from nyc_taxi_lake.quality.evaluate import evaluate_check

    result = evaluate_check(NullRate("n", "error", "fact_trips", "no_such_column", 0.0), tables)
    assert not result.passed
    assert result.kind == "null_rate"
    assert "no_such_column" in result.detail
