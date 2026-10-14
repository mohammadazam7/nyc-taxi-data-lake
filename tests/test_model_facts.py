from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession

pytestmark = pytest.mark.spark

CLEAN_COLUMNS = (
    "trip_id string, vendor_id int, pickup_at timestamp_ntz, dropoff_at timestamp_ntz, "
    "passenger_count int, trip_distance_mi double, rate_code_id int, "
    "store_and_forward boolean, pickup_zone_id int, dropoff_zone_id int, "
    "payment_type_id int, fare_amount decimal(10,2), extra_amount decimal(10,2), "
    "mta_tax decimal(10,2), tip_amount decimal(10,2), tolls_amount decimal(10,2), "
    "improvement_surcharge decimal(10,2), congestion_surcharge decimal(10,2), "
    "airport_fee decimal(10,2), total_amount decimal(10,2), pickup_date date"
)


def clean_row(
    trip_id: str,
    vendor_id: int | None = 2,
    rate_code_id: int | None = 1,
    payment_type_id: int | None = 1,
    pickup: datetime = datetime(2024, 1, 31, 23, 50),
    dropoff: datetime = datetime(2024, 2, 1, 0, 5),
) -> tuple[object, ...]:
    money = Decimal("1.00")
    return (
        trip_id, vendor_id, pickup, dropoff, 1, 2.5, rate_code_id, False, 132, 236,
        payment_type_id, Decimal("20.00"), money, money, money, money, money, money, money,
        Decimal("26.00"), pickup.date(),
    )  # fmt: skip


def clean_frame(spark: SparkSession, rows: list[tuple[object, ...]]) -> DataFrame:
    return spark.createDataFrame(rows, CLEAN_COLUMNS)


def test_fact_row_keys_and_measures(spark: SparkSession) -> None:
    from nyc_taxi_lake.model.dimensions import dim_payment_type, dim_vendor
    from nyc_taxi_lake.model.facts import fact_trips

    fact = fact_trips(clean_frame(spark, [clean_row("a")])).first()
    assert fact is not None

    # Trip crosses midnight at the month boundary: two different date keys.
    assert (fact["pickup_date_key"], fact["dropoff_date_key"]) == (20240131, 20240201)
    assert fact["trip_duration_s"] == 15 * 60
    assert fact["total_amount"] == Decimal("26.00")
    assert str(fact["pickup_date"]) == "2024-01-31"

    vendor = dim_vendor(spark).filter("vendor_id = 2").first()
    payment = dim_payment_type(spark).filter("payment_type_id = 1").first()
    assert vendor is not None and payment is not None
    assert fact["vendor_key"] == vendor["vendor_key"]
    assert fact["payment_type_key"] == payment["payment_type_key"]


def test_unlisted_and_null_codes_map_to_the_unknown_member(spark: SparkSession) -> None:
    from nyc_taxi_lake.model.dimensions import dim_rate_code, dim_vendor
    from nyc_taxi_lake.model.facts import fact_trips

    rows = [clean_row("odd", vendor_id=5, rate_code_id=None), clean_row("null", vendor_id=None)]
    facts = fact_trips(clean_frame(spark, rows)).collect()

    unknown_vendor = dim_vendor(spark).filter("vendor_id = -1").first()
    unknown_rate = dim_rate_code(spark).filter("rate_code_id = -1").first()
    assert unknown_vendor is not None and unknown_rate is not None
    assert {f["vendor_key"] for f in facts} == {unknown_vendor["vendor_key"]}
    by_id = {f["trip_id"]: f for f in facts}
    assert by_id["odd"]["rate_code_key"] == unknown_rate["rate_code_key"]


def test_every_fact_key_resolves_to_a_dimension_row(spark: SparkSession, tmp_path: Path) -> None:
    from nyc_taxi_lake.ingest.zone_lookup import write_sample_lookup
    from nyc_taxi_lake.model.dimensions import dim_payment_type, dim_rate_code, dim_vendor
    from nyc_taxi_lake.model.facts import fact_trips
    from nyc_taxi_lake.model.zones import dim_zone

    rows = [
        clean_row(str(i), vendor_id=v, rate_code_id=r, payment_type_id=p)
        for i, (v, r, p) in enumerate([(1, 1, 0), (2, 99, 6), (7, 5, 2), (3, 42, None)])
    ]
    fact = fact_trips(clean_frame(spark, rows))
    zones = dim_zone(spark, write_sample_lookup(tmp_path / "taxi_zone_lookup.csv"))

    checks = [
        ("vendor_key", dim_vendor(spark), "vendor_key"),
        ("rate_code_key", dim_rate_code(spark), "rate_code_key"),
        ("payment_type_key", dim_payment_type(spark), "payment_type_key"),
        ("pickup_zone_key", zones, "zone_key"),
        ("dropoff_zone_key", zones, "zone_key"),
    ]
    for fk, dim, pk in checks:
        orphans = fact.join(dim, fact[fk] == dim[pk], "left_anti").count()
        assert orphans == 0, f"{fk} has {orphans} rows with no match in the dimension"
