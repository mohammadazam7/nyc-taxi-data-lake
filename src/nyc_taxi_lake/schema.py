"""Canonical schema for TLC yellow taxi trip records.

TLC files drift over the years (column casing, int vs. double, new surcharge columns).
Everything that enters the raw zone is conformed to this schema so downstream jobs can
rely on one shape. Source: TLC "Data Dictionary - Yellow Taxi Trip Records".
"""

from __future__ import annotations

import pyarrow as pa

YELLOW_TRIP_SCHEMA = pa.schema(
    [
        pa.field("VendorID", pa.int32()),
        pa.field("tpep_pickup_datetime", pa.timestamp("us")),
        pa.field("tpep_dropoff_datetime", pa.timestamp("us")),
        pa.field("passenger_count", pa.float64()),
        pa.field("trip_distance", pa.float64()),
        pa.field("RatecodeID", pa.float64()),
        pa.field("store_and_fwd_flag", pa.string()),
        pa.field("PULocationID", pa.int32()),
        pa.field("DOLocationID", pa.int32()),
        pa.field("payment_type", pa.int64()),
        pa.field("fare_amount", pa.float64()),
        pa.field("extra", pa.float64()),
        pa.field("mta_tax", pa.float64()),
        pa.field("tip_amount", pa.float64()),
        pa.field("tolls_amount", pa.float64()),
        pa.field("improvement_surcharge", pa.float64()),
        pa.field("total_amount", pa.float64()),
        pa.field("congestion_surcharge", pa.float64()),
        pa.field("airport_fee", pa.float64()),
    ]
)

# TLC taxi zones are numbered 1-263; 264 and 265 mean "unknown" and "outside NYC" and
# do appear in real files, so they are valid IDs rather than errors.
MIN_ZONE_ID, MAX_ZONE_ID = 1, 265

# Older and newer files spell some columns differently.
COLUMN_ALIASES: dict[str, str] = {
    "Airport_fee": "airport_fee",
    "vendorid": "VendorID",
    "ratecodeid": "RatecodeID",
    "pulocationid": "PULocationID",
    "dolocationid": "DOLocationID",
}


def conform(table: pa.Table) -> pa.Table:
    """Rename aliased columns, add missing ones as nulls, drop extras and cast types."""
    renamed = table.rename_columns([COLUMN_ALIASES.get(c, c) for c in table.column_names])
    columns = []
    for field in YELLOW_TRIP_SCHEMA:
        if field.name in renamed.column_names:
            columns.append(renamed.column(field.name).cast(field.type, safe=False))
        else:
            columns.append(pa.nulls(renamed.num_rows, type=field.type))
    return pa.Table.from_arrays(columns, schema=YELLOW_TRIP_SCHEMA)
