from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest

from nyc_taxi_lake.analytics.results import AnalyticsReport, QueryResult

if TYPE_CHECKING:
    from pyspark.sql import SparkSession


@pytest.fixture(scope="session")
def _spark_teardown() -> Iterator[None]:
    yield
    from pyspark.sql import SparkSession

    active = SparkSession.getActiveSession()
    if active is not None:
        active.stop()


@pytest.fixture
def spark(_spark_teardown: None) -> SparkSession:
    """A local session shared by the tests.

    ``getOrCreate`` hands back the running session, so this is cheap after the first
    call. It also starts a new one if an earlier test stopped it, which the CLI does on
    exit (``nyc-lake clean`` owns its session), so test order does not matter.
    """
    pytest.importorskip("pyspark", reason="install the [spark] extra to run Spark tests")
    from nyc_taxi_lake.spark import get_spark

    session = get_spark("nyc-taxi-lake-tests", master="local[2]")
    session.sparkContext.setLogLevel("ERROR")
    return session


@pytest.fixture
def analytics_report() -> AnalyticsReport:
    """A two-month report with every query, small enough to check figures by hand."""
    q = QueryResult.from_records
    return AnalyticsReport(
        "yellow",
        "2024-01",
        "2024-02",
        (
            q(
                "monthly_revenue",
                [
                    "year",
                    "month",
                    "trips",
                    "revenue",
                    "fares",
                    "tips",
                    "other_charges",
                    "avg_revenue_per_trip",
                ],
                [
                    (2024, 1, 30, 600.0, 420.0, 60.0, 120.0, 20.0),
                    (2024, 2, 10, 200.0, 140.0, 20.0, 40.0, 20.0),
                ],
            ),
            q(
                "daily_trips",
                ["calendar_date", "trips", "revenue", "avg_distance_mi"],
                [("2024-01-01", 30, 600.0, 2.1), ("2024-02-01", 10, 200.0, 2.4)],
            ),
            q(
                "hourly_demand",
                ["day_of_week", "pickup_hour", "trips"],
                [(1, 8, 30), (4, 23, 10)],
            ),
            q(
                "busiest_pickup_zones",
                ["zone_id", "zone_name", "borough", "trips", "revenue"],
                [
                    (132, "JFK Airport", "Queens", 25, 500.0),
                    (7, "Astoria <&>", "Queens", 15, 300.0),
                ],
            ),
            q(
                "payment_mix",
                ["payment_type_id", "payment_type_name", "trips", "revenue", "tip_rate"],
                [(1, "Credit card", 30, 650.0, 0.19), (2, "Cash", 10, 150.0, None)],
            ),
        ),
    )
