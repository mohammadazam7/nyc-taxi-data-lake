"""Run the analytics queries with Spark SQL against the warehouse zone.

The star schema tables become temporary views named after their directories, which is
what the unqualified table names in the queries expect. Spark binds ``:start_key`` and
``:end_key`` itself, and it prunes ``fact_trips`` to the requested days through the
``pickup_date_key`` filter.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from pyspark.sql import SparkSession

from nyc_taxi_lake.analytics.queries import Query
from nyc_taxi_lake.analytics.results import QueryResult
from nyc_taxi_lake.paths import LakePath

STAR_TABLES = (
    "fact_trips",
    "dim_date",
    "dim_zone",
    "dim_vendor",
    "dim_rate_code",
    "dim_payment_type",
)


def register_warehouse(spark: SparkSession, warehouse_dir: LakePath) -> None:
    """Expose each star schema table under ``warehouse_dir`` as a temporary view."""
    missing = [t for t in STAR_TABLES if not (warehouse_dir / t).exists()]
    if missing:
        raise FileNotFoundError(
            f"no {', '.join(missing)} under {warehouse_dir}; run `nyc-lake model` first"
        )
    for table in STAR_TABLES:
        spark.read.parquet(str(warehouse_dir / table)).createOrReplaceTempView(table)


def run_query(spark: SparkSession, query: Query, params: Mapping[str, int]) -> QueryResult:
    frame = spark.sql(query.sql, args=dict(params))
    return QueryResult.from_records(query.name, frame.columns, frame.collect())


def run_queries(
    spark: SparkSession, queries: Iterable[Query], params: Mapping[str, int]
) -> list[QueryResult]:
    return [run_query(spark, query, params) for query in queries]
