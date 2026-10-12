from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

import pytest

from nyc_taxi_lake.months import Month
from nyc_taxi_lake.schema import YELLOW_TRIP_SCHEMA

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession

pytestmark = pytest.mark.spark

JAN = Month(2024, 1)


def good_trip(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "VendorID": 2,
        "tpep_pickup_datetime": datetime(2024, 1, 15, 8, 0),
        "tpep_dropoff_datetime": datetime(2024, 1, 15, 8, 20),
        "passenger_count": 1.0,
        "trip_distance": 3.1,
        "RatecodeID": 1.0,
        "store_and_fwd_flag": "N",
        "PULocationID": 161,
        "DOLocationID": 236,
        "payment_type": 1,
        "fare_amount": 18.4,
        "extra": 1.0,
        "mta_tax": 0.5,
        "tip_amount": 4.0,
        "tolls_amount": 0.0,
        "improvement_surcharge": 1.0,
        "total_amount": 27.4,
        "congestion_surcharge": 2.5,
        "airport_fee": 0.0,
    }
    row.update(overrides)
    return row


def frame(spark: SparkSession, rows: list[dict[str, Any]]) -> DataFrame:
    import pyarrow as pa

    return spark.createDataFrame(pa.Table.from_pylist(rows, schema=YELLOW_TRIP_SCHEMA))


def reason(spark: SparkSession, row: dict[str, Any]) -> str | None:
    from nyc_taxi_lake.clean.rules import tag_rejects

    (tagged,) = tag_rejects(frame(spark, [row]), JAN).collect()
    return tagged["reject_reason"]  # type: ignore[no-any-return]


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, None),
        ({"tpep_pickup_datetime": None}, "MISSING_TIMESTAMP"),
        ({"tpep_pickup_datetime": datetime(2023, 12, 31, 23, 59)}, "OUTSIDE_FILE_MONTH"),
        ({"tpep_pickup_datetime": datetime(2024, 2, 1, 0, 0)}, "OUTSIDE_FILE_MONTH"),
        ({"tpep_dropoff_datetime": datetime(2024, 1, 15, 7, 55)}, "DROPOFF_BEFORE_PICKUP"),
        ({"tpep_dropoff_datetime": datetime(2024, 1, 16, 8, 1)}, "TRIP_TOO_LONG"),
        ({"fare_amount": -18.4}, "NEGATIVE_AMOUNT"),
        ({"total_amount": -1.0}, "NEGATIVE_AMOUNT"),
        ({"trip_distance": -0.5}, "NEGATIVE_DISTANCE"),
        ({"passenger_count": 12.0}, "BAD_PASSENGER_COUNT"),
        ({"PULocationID": 999}, "UNKNOWN_ZONE"),
        ({"DOLocationID": 0}, "UNKNOWN_ZONE"),
        ({"DOLocationID": None}, "UNKNOWN_ZONE"),
        # Nulls in optional fields are kept: real TLC files have plenty of them.
        ({"passenger_count": None, "RatecodeID": None, "store_and_fwd_flag": None}, None),
        # 264/265 are TLC's own "unknown"/"outside NYC" zones, not errors.
        ({"PULocationID": 264, "DOLocationID": 265}, None),
        # Zero-length trips are odd but legal (meter started and stopped).
        ({"tpep_dropoff_datetime": datetime(2024, 1, 15, 8, 0)}, None),
    ],
)
def test_single_rule(spark: SparkSession, overrides: dict[str, Any], expected: str | None) -> None:
    assert reason(spark, good_trip(**overrides)) == expected


def test_first_broken_rule_wins(spark: SparkSession) -> None:
    row = good_trip(
        tpep_pickup_datetime=datetime(2002, 12, 31, 23, 0),
        tpep_dropoff_datetime=datetime(2002, 12, 31, 22, 0),
        fare_amount=-5.0,
        PULocationID=999,
    )
    assert reason(spark, row) == "OUTSIDE_FILE_MONTH"


def test_exact_duplicates_keep_one_copy(spark: SparkSession) -> None:
    from nyc_taxi_lake.clean.rules import tag_rejects

    rows = [good_trip(), good_trip(), good_trip(), good_trip(fare_amount=20.0)]
    got = sorted((r["reject_reason"] or "") for r in tag_rejects(frame(spark, rows), JAN).collect())
    assert got == ["", "", "DUPLICATE", "DUPLICATE"]


def test_duplicated_bad_row_keeps_its_real_reason(spark: SparkSession) -> None:
    from nyc_taxi_lake.clean.rules import tag_rejects

    bad = good_trip(fare_amount=-3.0)
    got = [r["reject_reason"] for r in tag_rejects(frame(spark, [bad, bad]), JAN).collect()]
    assert got == ["NEGATIVE_AMOUNT", "NEGATIVE_AMOUNT"]


def test_trip_id_distinguishes_null_from_value(spark: SparkSession) -> None:
    from nyc_taxi_lake.clean.rules import tag_rejects

    rows = [good_trip(passenger_count=None), good_trip(passenger_count=1.0)]
    ids = {r["trip_id"] for r in tag_rejects(frame(spark, rows), JAN).collect()}
    assert len(ids) == 2
