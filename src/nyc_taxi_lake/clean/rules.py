"""Validation rules for raw trips, each with a stable reason code.

A row that breaks any rule goes to quarantine tagged with the code of the *first* rule
it breaks, in the order listed in :func:`rules_for`. The codes are part of the data
contract: data-quality checks and dashboards group by them, so rename with care.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyspark.sql import Column, DataFrame, Window
from pyspark.sql import functions as F

from nyc_taxi_lake.months import Month
from nyc_taxi_lake.schema import MAX_ZONE_ID, MIN_ZONE_ID

MAX_TRIP_HOURS = 24
MAX_PASSENGERS = 9

DUPLICATE = "DUPLICATE"


@dataclass(frozen=True)
class Rule:
    code: str
    description: str
    violated: Column  # true when the row breaks the rule; null is treated as "passes"


def _ntz(value: str) -> Column:
    return F.lit(value).cast("timestamp_ntz")


def rules_for(month: Month) -> list[Rule]:
    """The rules for a raw file that claims to hold ``month``'s trips."""
    pickup, dropoff = F.col("tpep_pickup_datetime"), F.col("tpep_dropoff_datetime")
    month_start = _ntz(f"{month.key}-01 00:00:00")
    month_end = _ntz(f"{month.next().key}-01 00:00:00")

    def zone_ok(col: str) -> Column:
        return F.col(col).between(MIN_ZONE_ID, MAX_ZONE_ID)

    return [
        Rule(
            "MISSING_TIMESTAMP",
            "pickup or dropoff time is null",
            pickup.isNull() | dropoff.isNull(),
        ),
        Rule(
            "OUTSIDE_FILE_MONTH",
            "pickup is not in the month the file covers",
            (pickup < month_start) | (pickup >= month_end),
        ),
        Rule("DROPOFF_BEFORE_PICKUP", "dropoff is earlier than pickup", dropoff < pickup),
        Rule(
            "TRIP_TOO_LONG",
            f"trip lasted more than {MAX_TRIP_HOURS} hours",
            dropoff > pickup + F.make_dt_interval(hours=F.lit(MAX_TRIP_HOURS)),
        ),
        Rule(
            "NEGATIVE_AMOUNT",
            "fare or total amount is negative",
            (F.col("fare_amount") < 0) | (F.col("total_amount") < 0),
        ),
        Rule("NEGATIVE_DISTANCE", "trip distance is negative", F.col("trip_distance") < 0),
        Rule(
            "BAD_PASSENGER_COUNT",
            f"passenger count above {MAX_PASSENGERS}",
            F.col("passenger_count") > MAX_PASSENGERS,
        ),
        Rule(
            "UNKNOWN_ZONE",
            f"pickup or dropoff zone missing or outside {MIN_ZONE_ID}-{MAX_ZONE_ID}",
            ~F.coalesce(zone_ok("PULocationID") & zone_ok("DOLocationID"), F.lit(False)),
        ),
    ]


def trip_id(columns: list[str]) -> Column:
    """Deterministic key from every source column.

    TLC rows have no ID. Hashing the JSON of the whole row (JSON keeps nulls distinct from
    empty strings and from each other's positions) gives identical rows identical keys,
    which is exactly what deduplication needs, and gives later stages a stable key.
    """
    return F.sha2(F.to_json(F.struct(*[F.col(c) for c in columns])), 256)


def tag_rejects(raw: DataFrame, month: Month) -> DataFrame:
    """Add ``trip_id`` and ``reject_reason`` (null for rows that pass) to ``raw``."""
    with_id = raw.withColumn("trip_id", trip_id(raw.columns))
    first_copy = F.row_number().over(Window.partitionBy("trip_id").orderBy(F.lit(1))) == 1

    reason: Column = F.lit(None).cast("string")
    # Build from the last rule backwards so the first rule ends up outermost and wins.
    checks: list[tuple[str, Column]] = [(r.code, r.violated) for r in rules_for(month)]
    checks.append((DUPLICATE, ~first_copy))
    for code, violated in reversed(checks):
        reason = F.when(F.coalesce(violated, F.lit(False)), F.lit(code)).otherwise(reason)
    return with_id.withColumn("reject_reason", reason)
