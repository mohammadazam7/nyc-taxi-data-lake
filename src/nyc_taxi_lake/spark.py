"""SparkSession factory shared by the jobs and the tests."""

from __future__ import annotations

from pyspark.sql import SparkSession


def get_spark(app_name: str = "nyc-taxi-lake", master: str | None = None) -> SparkSession:
    """Return a session configured the same way locally and on Glue.

    * UTC session time zone, so nothing shifts the TLC timestamps (which are naive
      New York local times and are read as ``TIMESTAMP_NTZ``).
    * Dynamic partition overwrite, so rewriting one month only replaces that month's
      partitions. Re-running a job is idempotent.
    """
    builder = (
        SparkSession.builder.appName(app_name)
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.sources.partitionOverwriteMode", "dynamic")
        .config("spark.sql.parquet.inferTimestampNTZ.enabled", "true")
    )
    if master:
        builder = builder.master(master).config("spark.sql.shuffle.partitions", "4")
    return builder.getOrCreate()
