"""Dimension builders.

Surrogate keys
--------------
``dim_date`` uses the conventional ``yyyymmdd`` integer. The other dimensions use a
64-bit hash of the dimension name and its natural key. That key is the same on every run
and every machine, so the fact table can be rebuilt one month at a time without a key
lookup table and without the dimensions having to be rebuilt first. A test checks the
keys stay unique.

All dimensions are SCD type 1: a changed attribute (say TLC renames a vendor) overwrites
the old value, because no report needs the old names.
"""

from __future__ import annotations

from datetime import date, timedelta

from pyspark.sql import Column, DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import IntegerType, StringType, StructField, StructType

from nyc_taxi_lake.model.reference import PAYMENT_TYPES, RATE_CODES, VENDORS, with_unknown


def surrogate_key(dimension: str, natural_key: Column) -> Column:
    """Stable BIGINT key for ``natural_key`` within ``dimension``."""
    return F.xxhash64(F.lit(dimension), natural_key.cast("string"))


def date_key(day: Column) -> Column:
    """``yyyymmdd`` as an integer, e.g. 2024-01-15 -> 20240115."""
    return F.date_format(day, "yyyyMMdd").cast("int")


def _code_dim(spark: SparkSession, name: str, codes: dict[int, str], prefix: str) -> DataFrame:
    schema = StructType(
        [
            StructField(f"{prefix}_id", IntegerType(), nullable=False),
            StructField(f"{prefix}_name", StringType(), nullable=False),
        ]
    )
    rows = spark.createDataFrame(with_unknown(codes), schema)
    key = surrogate_key(name, F.col(f"{prefix}_id")).alias(f"{prefix}_key")
    return rows.select(key, f"{prefix}_id", f"{prefix}_name")


def dim_vendor(spark: SparkSession) -> DataFrame:
    return _code_dim(spark, "dim_vendor", VENDORS, "vendor")


def dim_rate_code(spark: SparkSession) -> DataFrame:
    return _code_dim(spark, "dim_rate_code", RATE_CODES, "rate_code")


def dim_payment_type(spark: SparkSession) -> DataFrame:
    return _code_dim(spark, "dim_payment_type", PAYMENT_TYPES, "payment_type")


def dim_date(spark: SparkSession, first: date, last: date) -> DataFrame:
    """One row per calendar day from ``first`` to ``last`` inclusive.

    Holidays are not modelled; weekday versus weekend is what the trip analysis uses.
    """
    if last < first:
        raise ValueError(f"last ({last}) is before first ({first})")
    days = (last - first).days + 1
    frame = spark.createDataFrame(
        [(first + timedelta(days=i),) for i in range(days)], "calendar_date date"
    )
    d = F.col("calendar_date")
    return frame.select(
        date_key(d).alias("date_key"),
        d,
        F.year(d).alias("year"),
        F.quarter(d).alias("quarter"),
        F.month(d).alias("month"),
        F.date_format(d, "MMMM").alias("month_name"),
        F.dayofmonth(d).alias("day_of_month"),
        # ISO numbering: Monday = 1 ... Sunday = 7.
        (((F.dayofweek(d) + 5) % 7) + 1).alias("day_of_week"),
        F.date_format(d, "EEEE").alias("day_name"),
        F.weekofyear(d).alias("iso_week"),
        F.dayofweek(d).isin(1, 7).alias("is_weekend"),
    )
