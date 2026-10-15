"""Keep the Redshift DDL in step with the Parquet files the model job writes.

``COPY ... FORMAT AS PARQUET`` matches columns by position and fails on a type it can't
convert, so a column added to a builder without a matching DDL change would only show
up as a failed load in AWS. These tests catch it here instead.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from nyc_taxi_lake.model.reference import PAYMENT_TYPES, RATE_CODES, VENDORS

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession

DDL = Path(__file__).resolve().parents[1] / "sql" / "redshift" / "star_schema.sql"

# Spark type (simpleString) -> the Redshift types COPY can load it into.
REDSHIFT_TYPES = {
    "int": {"INTEGER"},
    "bigint": {"BIGINT"},
    "string": {"VARCHAR", "CHAR"},
    "date": {"DATE"},
    "boolean": {"BOOLEAN"},
    "timestamp_ntz": {"TIMESTAMP"},
    "double": {"DOUBLE PRECISION"},
    "decimal(10,2)": {"DECIMAL(10,2)"},
}

# Partition columns live in the directory names, not in the files COPY reads.
PARTITION_COLUMNS = {"fact_trips": {"pickup_date"}}

_TABLE = re.compile(r"CREATE TABLE IF NOT EXISTS taxi\.(\w+) \((.*?)\n\)", re.S)
_COLUMN = re.compile(r"^\s*(\w+)\s+(DOUBLE PRECISION|\w+(?:\(\s*\d+(?:,\s*\d+)?\))?)")


def parse_ddl(text: str) -> dict[str, list[tuple[str, str]]]:
    """``{table: [(column, TYPE), ...]}`` in declaration order."""
    text = re.sub(r"--[^\n]*", "", text)
    tables: dict[str, list[tuple[str, str]]] = {}
    for name, body in _TABLE.findall(text):
        columns = []
        for line in body.splitlines():
            match = _COLUMN.match(line)
            if match and match.group(1).upper() != "PRIMARY":
                columns.append((match.group(1), re.sub(r"\s+", "", match.group(2))))
        tables[name] = columns
    return tables


def base_type(redshift_type: str) -> str:
    """``VARCHAR(64)`` -> ``VARCHAR``; decimals keep precision and scale."""
    if redshift_type.startswith("DECIMAL") or redshift_type == "DOUBLEPRECISION":
        return redshift_type.replace("DOUBLEPRECISION", "DOUBLE PRECISION")
    return redshift_type.split("(")[0]


def varchar_length(redshift_type: str) -> int:
    match = re.fullmatch(r"VARCHAR\((\d+)\)", redshift_type)
    assert match, f"{redshift_type} is not a VARCHAR(n)"
    return int(match.group(1))


@pytest.fixture(scope="module")
def ddl() -> dict[str, list[tuple[str, str]]]:
    return parse_ddl(DDL.read_text())


def test_parser_reads_every_table(ddl: dict[str, list[tuple[str, str]]]) -> None:
    assert set(ddl) == {
        "dim_date",
        "dim_zone",
        "dim_vendor",
        "dim_rate_code",
        "dim_payment_type",
        "fact_trips",
    }
    assert ddl["dim_vendor"] == [
        ("vendor_key", "BIGINT"),
        ("vendor_id", "INTEGER"),
        ("vendor_name", "VARCHAR(64)"),
    ]


@pytest.mark.parametrize(
    ("table", "codes"),
    [("dim_vendor", VENDORS), ("dim_rate_code", RATE_CODES), ("dim_payment_type", PAYMENT_TYPES)],
)
def test_code_names_fit_their_columns(
    ddl: dict[str, list[tuple[str, str]]], table: str, codes: dict[int, str]
) -> None:
    name_type = dict(ddl[table])[f"{table.removeprefix('dim_')}_name"]
    assert max(len(name) for name in codes.values()) <= varchar_length(name_type)


def _built_tables(spark: SparkSession, tmp_path: Path) -> dict[str, DataFrame]:
    from test_model_facts import clean_frame, clean_row

    from nyc_taxi_lake.ingest.zone_lookup import write_sample_lookup
    from nyc_taxi_lake.model.dimensions import (
        dim_date,
        dim_payment_type,
        dim_rate_code,
        dim_vendor,
    )
    from nyc_taxi_lake.model.facts import fact_trips
    from nyc_taxi_lake.model.zones import dim_zone

    return {
        "dim_date": dim_date(spark, date(2024, 1, 1), date(2024, 1, 2)),
        "dim_zone": dim_zone(spark, write_sample_lookup(tmp_path / "zones.csv")),
        "dim_vendor": dim_vendor(spark),
        "dim_rate_code": dim_rate_code(spark),
        "dim_payment_type": dim_payment_type(spark),
        "fact_trips": fact_trips(clean_frame(spark, [clean_row("a")])),
    }


@pytest.mark.spark
def test_ddl_matches_the_parquet_the_model_job_writes(
    spark: SparkSession, tmp_path: Path, ddl: dict[str, list[tuple[str, str]]]
) -> None:
    for table, frame in _built_tables(spark, tmp_path).items():
        skip = PARTITION_COLUMNS.get(table, set())
        spark_columns = [
            (f.name, f.dataType.simpleString()) for f in frame.schema if f.name not in skip
        ]
        assert [c for c, _ in ddl[table]] == [c for c, _ in spark_columns], table
        for (column, rs_type), (_, spark_type) in zip(ddl[table], spark_columns, strict=True):
            allowed = REDSHIFT_TYPES[spark_type]
            assert base_type(rs_type) in allowed, f"{table}.{column}: {rs_type} vs {spark_type}"
