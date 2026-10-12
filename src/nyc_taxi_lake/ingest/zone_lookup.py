"""The TLC taxi zone lookup file, and a placeholder for offline runs.

Kept free of Spark so ingest and its tests work without the [spark] extra.
"""

from __future__ import annotations

import csv
from pathlib import Path

from nyc_taxi_lake.schema import MAX_ZONE_ID

LOOKUP_FILE = "taxi_zone_lookup.csv"
LOOKUP_COLUMNS = ("LocationID", "Borough", "Zone", "service_zone")

_SAMPLE_BOROUGHS = ("Manhattan", "Queens", "Brooklyn", "Bronx", "Staten Island", "EWR")


def write_sample_lookup(path: Path) -> Path:
    """Write a synthetic lookup with zones 1..265 named ``Sample zone N``.

    The names are placeholders, not TLC's. Use the real file for anything you publish.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(LOOKUP_COLUMNS)
        for zone_id in range(1, MAX_ZONE_ID + 1):
            borough = _SAMPLE_BOROUGHS[zone_id % len(_SAMPLE_BOROUGHS)]
            writer.writerow([zone_id, borough, f"Sample zone {zone_id}", "Sample"])
    return path
