from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from nyc_taxi_lake.analytics.queries import load_queries, month_bounds
from nyc_taxi_lake.analytics.results import QueryResult
from nyc_taxi_lake.config import Settings
from nyc_taxi_lake.ingest.raw_zone import write_partition
from nyc_taxi_lake.ingest.sample import generate_month
from nyc_taxi_lake.ingest.zone_lookup import write_sample_lookup
from nyc_taxi_lake.months import Month

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession

pytestmark = pytest.mark.spark

JAN, FEB = Month(2024, 1), Month(2024, 2)


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Two modelled synthetic months; returns the warehouse directory for yellow.

    Built once for the module: modelling is the slow part, and the queries only read it.
    """
    pytest.importorskip("pyspark", reason="install the [spark] extra to run Spark tests")
    from nyc_taxi_lake.clean.job import clean_month
    from nyc_taxi_lake.model.job import model_month, zone_lookup_path
    from nyc_taxi_lake.spark import get_spark

    spark = get_spark("nyc-taxi-lake-tests", master="local[2]")
    lake = tmp_path_factory.mktemp("lake")
    settings = Settings(
        lake_root=lake,
        tlc_base_url="https://example.test/trip-data",
        taxi_type="yellow",
        http_timeout_s=5,
        http_retries=1,
    )
    write_sample_lookup(zone_lookup_path(settings))
    for month in (JAN, FEB):
        write_partition(generate_month(month, rows=1_500), settings.raw_root, "yellow", month, "t")
        clean_month(spark, settings, month)
        model_month(spark, settings, month)
    return lake / "warehouse" / "yellow"


@pytest.fixture(scope="module")
def january(warehouse: Path) -> dict[str, QueryResult]:
    from nyc_taxi_lake.analytics.spark_runner import register_warehouse, run_queries
    from nyc_taxi_lake.spark import get_spark

    spark = get_spark("nyc-taxi-lake-tests", master="local[2]")
    register_warehouse(spark, warehouse)
    results = run_queries(spark, load_queries(), month_bounds(JAN, JAN))
    return {r.name: r for r in results}


def _january_facts(spark: SparkSession, warehouse: Path) -> DataFrame:
    facts = spark.read.parquet(str(warehouse / "fact_trips"))
    return facts.filter("pickup_date_key BETWEEN 20240101 AND 20240131")


def test_totals_agree_across_queries_and_with_the_fact_table(
    spark: SparkSession, warehouse: Path, january: dict[str, QueryResult]
) -> None:
    from pyspark.sql import functions as F

    facts = _january_facts(spark, warehouse)
    trips = facts.count()
    revenue = float(facts.agg(F.sum("total_amount")).first()[0])  # type: ignore[index]

    monthly = january["monthly_revenue"].records()
    assert [(m["year"], m["month"]) for m in monthly] == [(2024, 1)]
    assert monthly[0]["trips"] == trips
    assert monthly[0]["revenue"] == pytest.approx(revenue)

    for name in ("daily_trips", "hourly_demand", "payment_mix"):
        assert sum(january[name].column("trips")) == trips, name  # type: ignore[arg-type]


def test_month_range_excludes_other_months(january: dict[str, QueryResult]) -> None:
    days = january["daily_trips"].column("calendar_date")
    assert days[0] == "2024-01-01"
    assert days[-1] == "2024-01-31"
    assert days == sorted(days)


def test_hourly_demand_covers_the_week_and_the_day(january: dict[str, QueryResult]) -> None:
    hourly = january["hourly_demand"]
    assert set(hourly.column("day_of_week")) <= set(range(1, 8))
    assert set(hourly.column("pickup_hour")) <= set(range(24))


def test_busiest_zones_are_ranked_and_capped(january: dict[str, QueryResult]) -> None:
    trips = january["busiest_pickup_zones"].column("trips")
    assert 0 < len(trips) <= 15
    assert trips == sorted(trips, reverse=True)  # type: ignore[type-var]


def test_missing_tables_are_reported(spark: SparkSession, tmp_path: Path) -> None:
    from nyc_taxi_lake.analytics.spark_runner import register_warehouse

    with pytest.raises(FileNotFoundError, match="nyc-lake model"):
        register_warehouse(spark, tmp_path)
