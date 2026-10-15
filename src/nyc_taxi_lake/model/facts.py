"""``fact_trips``: one row per clean trip, keyed to the dimensions.

The grain is a single trip. Foreign keys are computed with the same
:func:`~nyc_taxi_lake.model.dimensions.surrogate_key` the dimensions use, so a month of
facts can be built on its own without joining to the dimension tables. Codes that are
null or not in the TLC dictionary resolve to the unknown member instead of producing a
dangling key.
"""

from __future__ import annotations

from collections.abc import Iterable

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from nyc_taxi_lake.model.dimensions import date_key, surrogate_key
from nyc_taxi_lake.model.reference import PAYMENT_TYPES, RATE_CODES, UNKNOWN_CODE, VENDORS

MONEY_COLUMNS = (
    "fare_amount",
    "extra_amount",
    "mta_tax",
    "tip_amount",
    "tolls_amount",
    "improvement_surcharge",
    "congestion_surcharge",
    "airport_fee",
    "total_amount",
)


def known_or_unknown(code: Column, known: Iterable[int]) -> Column:
    """``code`` if it is one of ``known``, otherwise the unknown member's code."""
    return F.when(code.isin(*sorted(known)), code).otherwise(F.lit(UNKNOWN_CODE))


def _zone_key(zone_id: Column) -> Column:
    # The clean stage already rejects missing and out-of-range zones; the coalesce keeps
    # the key valid if this job is ever pointed at data that skipped that rule.
    return surrogate_key("dim_zone", F.coalesce(zone_id, F.lit(UNKNOWN_CODE)))


def fact_trips(clean: DataFrame) -> DataFrame:
    """Build the fact rows for a set of clean trips."""
    pickup, dropoff = F.col("pickup_at"), F.col("dropoff_at")
    duration_s = F.unix_timestamp(dropoff.cast("timestamp")) - F.unix_timestamp(
        pickup.cast("timestamp")
    )
    vendor = known_or_unknown(F.col("vendor_id"), VENDORS)
    rate_code = known_or_unknown(F.col("rate_code_id"), RATE_CODES)
    payment_type = known_or_unknown(F.col("payment_type_id"), PAYMENT_TYPES)
    vendor_key = surrogate_key("dim_vendor", vendor).alias("vendor_key")
    rate_code_key = surrogate_key("dim_rate_code", rate_code).alias("rate_code_key")
    payment_type_key = surrogate_key("dim_payment_type", payment_type).alias("payment_type_key")
    return clean.select(
        "trip_id",
        date_key(F.to_date(pickup)).alias("pickup_date_key"),
        date_key(F.to_date(dropoff)).alias("dropoff_date_key"),
        _zone_key(F.col("pickup_zone_id")).alias("pickup_zone_key"),
        _zone_key(F.col("dropoff_zone_id")).alias("dropoff_zone_key"),
        vendor_key,
        rate_code_key,
        payment_type_key,
        pickup,
        dropoff,
        duration_s.cast("int").alias("trip_duration_s"),
        "passenger_count",
        "trip_distance_mi",
        "store_and_forward",
        *MONEY_COLUMNS,
        # Partition column for the warehouse zone; the same layout as the clean zone.
        F.to_date(pickup).alias("pickup_date"),
    )
