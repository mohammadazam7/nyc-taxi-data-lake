from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pytest

from nyc_taxi_lake.model.reference import PAYMENT_TYPES, UNKNOWN_CODE, with_unknown

if TYPE_CHECKING:
    from pyspark.sql import SparkSession


def test_with_unknown_puts_unknown_member_first_and_sorts_codes() -> None:
    rows = with_unknown({2: "b", 1: "a"})
    assert rows == [(UNKNOWN_CODE, "Unknown"), (1, "a"), (2, "b")]


def test_payment_type_codes_match_the_data_dictionary() -> None:
    assert set(PAYMENT_TYPES) == {0, 1, 2, 3, 4, 5, 6}


@pytest.mark.spark
def test_code_dims_have_unique_stable_keys(spark: SparkSession) -> None:
    from nyc_taxi_lake.model.dimensions import dim_payment_type, dim_rate_code, dim_vendor

    for build in (dim_vendor, dim_rate_code, dim_payment_type):
        first = {tuple(r) for r in build(spark).collect()}
        second = {tuple(r) for r in build(spark).collect()}
        assert first == second
        keys = [r[0] for r in first]
        assert len(keys) == len(set(keys))
        assert UNKNOWN_CODE in {r[1] for r in first}


@pytest.mark.spark
def test_same_code_in_different_dims_gets_different_keys(spark: SparkSession) -> None:
    from nyc_taxi_lake.model.dimensions import dim_payment_type, dim_vendor

    vendor_1 = dim_vendor(spark).filter("vendor_id = 1").first()
    payment_1 = dim_payment_type(spark).filter("payment_type_id = 1").first()
    assert vendor_1 is not None and payment_1 is not None
    assert vendor_1["vendor_key"] != payment_1["payment_type_key"]


@pytest.mark.spark
def test_dim_date_attributes(spark: SparkSession) -> None:
    from nyc_taxi_lake.model.dimensions import dim_date

    rows = {
        r["calendar_date"]: r
        for r in dim_date(spark, date(2024, 1, 1), date(2024, 1, 31)).collect()
    }
    assert len(rows) == 31

    monday = rows[date(2024, 1, 1)]
    assert monday["date_key"] == 20240101
    assert (monday["day_of_week"], monday["day_name"], monday["is_weekend"]) == (1, "Monday", False)
    assert (monday["quarter"], monday["month_name"], monday["iso_week"]) == (1, "January", 1)

    sunday = rows[date(2024, 1, 7)]
    assert (sunday["day_of_week"], sunday["is_weekend"]) == (7, True)


@pytest.mark.spark
def test_dim_date_rejects_reversed_range(spark: SparkSession) -> None:
    from nyc_taxi_lake.model.dimensions import dim_date

    with pytest.raises(ValueError, match="before"):
        dim_date(spark, date(2024, 2, 1), date(2024, 1, 1))
