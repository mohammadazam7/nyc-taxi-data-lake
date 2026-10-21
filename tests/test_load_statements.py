from __future__ import annotations

import re
from pathlib import Path

import pytest

from nyc_taxi_lake.load.statements import DIMENSIONS, FACT, date_key_range, month_load
from nyc_taxi_lake.months import Month


def test_date_key_range_covers_the_month() -> None:
    assert date_key_range(Month(2024, 2)) == (20240201, 20240229)
    assert date_key_range(Month(2023, 2)) == (20230201, 20230228)
    assert date_key_range(Month(2024, 12)) == (20241201, 20241231)


def test_month_load_rewrites_dims_and_replaces_the_months_facts() -> None:
    sql = month_load("s3://lake/warehouse/yellow/", Month(2024, 1))
    assert len(sql) == 2 * len(DIMENSIONS) + 2
    assert sql[0] == "DELETE FROM taxi.dim_date"
    assert sql[1] == (
        "COPY taxi.dim_date FROM 's3://lake/warehouse/yellow/dim_date/' "
        "IAM_ROLE default FORMAT AS PARQUET"
    )
    assert sql[-2] == (
        "DELETE FROM taxi.fact_trips WHERE pickup_date_key BETWEEN 20240101 AND 20240131"
    )
    assert sql[-1] == (
        "COPY taxi.fact_trips FROM 's3://lake/warehouse/yellow/fact_trips/pickup_date=2024-01-' "
        "IAM_ROLE default FORMAT AS PARQUET"
    )


def test_never_truncates() -> None:
    # TRUNCATE commits the transaction in Redshift; a failed COPY would leave empty dims.
    assert not any("TRUNCATE" in s for s in month_load("s3://lake/w", Month(2024, 1)))


def test_explicit_role_is_quoted() -> None:
    role = "arn:aws:iam::123456789012:role/copy"
    sql = month_load("s3://lake/w", Month(2024, 1), iam_role=role)
    assert sql[1].endswith(f"IAM_ROLE '{role}' FORMAT AS PARQUET")


def test_quotes_in_the_uri_are_escaped() -> None:
    sql = month_load("s3://lake/o'brien", Month(2024, 1))
    assert "'s3://lake/o''brien/dim_date/'" in sql[1]


@pytest.mark.parametrize("uri", ["./lake/warehouse/yellow", "s3a://lake/warehouse"])
def test_rejects_non_s3_sources(uri: str) -> None:
    with pytest.raises(ValueError, match="S3"):
        month_load(uri, Month(2024, 1))


def test_rejects_an_unsafe_schema() -> None:
    with pytest.raises(ValueError):
        month_load("s3://lake/w", Month(2024, 1), schema="taxi; drop table x")


def test_loads_every_table_the_ddl_creates() -> None:
    ddl = (Path(__file__).parent.parent / "sql" / "redshift" / "star_schema.sql").read_text()
    created = set(re.findall(r"CREATE TABLE IF NOT EXISTS taxi\.(\w+)", ddl))
    assert created == {*DIMENSIONS, FACT}
