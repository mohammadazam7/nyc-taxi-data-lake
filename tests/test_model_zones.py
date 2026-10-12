from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from nyc_taxi_lake.model.zones import LOOKUP_COLUMNS, write_sample_lookup

if TYPE_CHECKING:
    from pyspark.sql import SparkSession


def test_sample_lookup_has_tlc_columns_and_all_zone_ids(tmp_path: Path) -> None:
    path = write_sample_lookup(tmp_path / "ref" / "taxi_zone_lookup.csv")
    with path.open() as fh:
        rows = list(csv.reader(fh))
    assert tuple(rows[0]) == LOOKUP_COLUMNS
    assert [int(r[0]) for r in rows[1:]] == list(range(1, 266))


@pytest.mark.spark
def test_dim_zone_adds_unknown_member_and_unique_keys(spark: SparkSession, tmp_path: Path) -> None:
    from nyc_taxi_lake.model.zones import dim_zone

    zones = dim_zone(spark, write_sample_lookup(tmp_path / "zones.csv")).collect()
    assert len(zones) == 266
    assert len({z["zone_key"] for z in zones}) == 266
    unknown = next(z for z in zones if z["zone_id"] == -1)
    assert unknown["zone_name"] == "Unknown"


@pytest.mark.spark
def test_dim_zone_tolerates_blank_names_and_duplicate_ids(
    spark: SparkSession, tmp_path: Path
) -> None:
    from nyc_taxi_lake.model.zones import dim_zone

    path = tmp_path / "zones.csv"
    path.write_text(
        "LocationID,Borough,Zone,service_zone\n"
        "1,EWR,Newark Airport,EWR\n"
        "1,EWR,Newark Airport,EWR\n"
        "2,,,\n"
        ",Queens,No id,Boro Zone\n"
    )
    zones = {z["zone_id"]: z for z in dim_zone(spark, path).collect()}
    assert sorted(zones) == [-1, 1, 2]
    assert zones[1]["zone_name"] == "Newark Airport"
    assert zones[2]["borough"] == "Unknown"
