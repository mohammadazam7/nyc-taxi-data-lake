"""``dim_zone`` from the TLC taxi zone lookup.

TLC publishes the zone list as ``taxi_zone_lookup.csv`` next to the trip files, with the
columns ``LocationID, Borough, Zone, service_zone``. In AWS the file is landed in the raw
zone alongside the trips. Offline, ``ingest.zone_lookup.write_sample_lookup`` writes a
placeholder file with the same shape so the model job and its tests run without network
access.
"""

from __future__ import annotations

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from nyc_taxi_lake.model.dimensions import surrogate_key
from nyc_taxi_lake.model.reference import UNKNOWN_CODE, UNKNOWN_NAME
from nyc_taxi_lake.paths import LakePath


def dim_zone(spark: SparkSession, lookup_csv: LakePath) -> DataFrame:
    """Zones from the lookup file plus the unknown member, one row per ``zone_id``."""
    lookup = spark.read.csv(
        str(lookup_csv),
        header=True,
        schema="LocationID int, Borough string, Zone string, service_zone string",
    )
    zones = lookup.select(
        F.col("LocationID").alias("zone_id"),
        F.coalesce(F.trim("Zone"), F.lit(UNKNOWN_NAME)).alias("zone_name"),
        F.coalesce(F.trim("Borough"), F.lit(UNKNOWN_NAME)).alias("borough"),
        F.coalesce(F.trim("service_zone"), F.lit(UNKNOWN_NAME)).alias("service_zone"),
    ).filter(F.col("zone_id").isNotNull())
    # The published file has one row per LocationID; keep the build safe if it ever doesn't.
    zones = zones.dropDuplicates(["zone_id"])

    unknown = spark.createDataFrame(
        [(UNKNOWN_CODE, UNKNOWN_NAME, UNKNOWN_NAME, UNKNOWN_NAME)],
        "zone_id int, zone_name string, borough string, service_zone string",
    )
    all_zones = unknown.unionByName(zones)
    return all_zones.select(
        surrogate_key("dim_zone", F.col("zone_id")).alias("zone_key"),
        "zone_id",
        "zone_name",
        "borough",
        "service_zone",
    )
