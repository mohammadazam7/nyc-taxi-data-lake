"""Generate synthetic trip files that match the TLC yellow schema.

Used by tests, CI and offline demos. The generator deliberately injects the same kinds
of defects found in real TLC data (duplicates, negative fares, dropoff before pickup,
trips outside the file's month, unknown zones) so the cleaning and data-quality stages
have something real to catch.
"""

from __future__ import annotations

import calendar
import random
from datetime import datetime, timedelta

import pyarrow as pa

from nyc_taxi_lake.months import Month
from nyc_taxi_lake.schema import YELLOW_TRIP_SCHEMA

# A few busy TLC zone IDs (Midtown, JFK, LaGuardia, Upper East Side, ...)
_BUSY_ZONES = [161, 162, 163, 230, 236, 237, 132, 138, 186, 48, 68, 79, 142, 170]
_PAYMENT_WEIGHTS = {1: 0.72, 2: 0.22, 3: 0.03, 4: 0.03}  # card, cash, no charge, dispute

DEFECT_RATE = 0.02


def generate_month(month: Month, rows: int, seed: int = 7) -> pa.Table:
    rng = random.Random(seed + month.year * 100 + month.month)
    days = calendar.monthrange(month.year, month.month)[1]
    start = datetime(month.year, month.month, 1)

    cols: dict[str, list[object]] = {f.name: [] for f in YELLOW_TRIP_SCHEMA}
    for _ in range(rows):
        pickup = start + timedelta(seconds=rng.randrange(days * 86_400))
        miles = round(max(0.1, rng.lognormvariate(0.6, 0.8)), 2)
        minutes = max(1.0, miles * rng.uniform(2.5, 6.0))
        dropoff = pickup + timedelta(minutes=minutes)
        fare = round(3.0 + miles * 2.5 + minutes * 0.5, 2)
        payment = rng.choices(list(_PAYMENT_WEIGHTS), weights=list(_PAYMENT_WEIGHTS.values()))[0]
        tip = round(fare * rng.uniform(0.1, 0.25), 2) if payment == 1 else 0.0
        pu = rng.choice(_BUSY_ZONES) if rng.random() < 0.6 else rng.randint(1, 263)
        do = rng.choice(_BUSY_ZONES) if rng.random() < 0.6 else rng.randint(1, 263)
        airport = 1.75 if pu in (132, 138) else 0.0
        congestion = 2.5
        total = round(fare + 1.0 + 0.5 + tip + 0.3 + congestion + airport, 2)

        row: dict[str, object] = {
            "VendorID": rng.choice([1, 2]),
            "tpep_pickup_datetime": pickup,
            "tpep_dropoff_datetime": dropoff,
            "passenger_count": float(rng.choice([1, 1, 1, 1, 2, 2, 3, 4, 5])),
            "trip_distance": miles,
            "RatecodeID": 2.0 if pu == 132 else 1.0,
            "store_and_fwd_flag": "N",
            "PULocationID": pu,
            "DOLocationID": do,
            "payment_type": payment,
            "fare_amount": fare,
            "extra": 1.0,
            "mta_tax": 0.5,
            "tip_amount": tip,
            "tolls_amount": 0.0,
            "improvement_surcharge": 0.3,
            "total_amount": total,
            "congestion_surcharge": congestion,
            "airport_fee": airport,
        }
        if rng.random() < DEFECT_RATE:
            _inject_defect(row, rng)
        for name in cols:
            cols[name].append(row[name])

    # Exact duplicates, as seen when vendors resubmit batches.
    for idx in rng.sample(range(rows), k=max(1, rows // 200)):
        for name in cols:
            cols[name].append(cols[name][idx])

    return pa.Table.from_pydict(cols, schema=YELLOW_TRIP_SCHEMA)


def _inject_defect(row: dict[str, object], rng: random.Random) -> None:
    kind = rng.choice(["negative_fare", "time_travel", "wrong_month", "bad_zone", "null_count"])
    if kind == "negative_fare":
        row["fare_amount"] = -abs(float(row["fare_amount"]))  # type: ignore[arg-type]
        row["total_amount"] = -abs(float(row["total_amount"]))  # type: ignore[arg-type]
    elif kind == "time_travel":
        row["tpep_dropoff_datetime"] = row["tpep_pickup_datetime"] - timedelta(minutes=5)  # type: ignore[operator]
    elif kind == "wrong_month":
        row["tpep_pickup_datetime"] = datetime(2002, 12, 31, 23, 59)
        row["tpep_dropoff_datetime"] = datetime(2003, 1, 1, 0, 10)
    elif kind == "bad_zone":
        row["PULocationID"] = 999
    else:
        row["passenger_count"] = None
