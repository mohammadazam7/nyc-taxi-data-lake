"""SQL that loads one modelled month from the warehouse zone into Redshift.

A month load is one transaction:

* the dimensions are SCD-1 and rewritten in full by every model run, so each one is
  emptied and copied again;
* the month's facts are deleted by pickup date key and copied from the month's
  ``pickup_date=YYYY-MM-*`` partitions, so loading a month twice leaves the same rows.

``DELETE`` is used rather than ``TRUNCATE`` because ``TRUNCATE`` commits the open
transaction in Redshift, which would leave a dimension empty if a later ``COPY`` failed.
"""

from __future__ import annotations

import calendar
import re

from nyc_taxi_lake.months import Month

DIMENSIONS = ("dim_date", "dim_zone", "dim_vendor", "dim_rate_code", "dim_payment_type")
FACT = "fact_trips"

_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")


def _identifier(name: str) -> str:
    if not _IDENTIFIER.match(name):
        raise ValueError(f"not a plain SQL identifier: {name!r}")
    return name


def _literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def date_key_range(month: Month) -> tuple[int, int]:
    """First and last ``dim_date.date_key`` (``YYYYMMDD``) in ``month``."""
    last_day = calendar.monthrange(month.year, month.month)[1]
    base = month.year * 10_000 + month.month * 100
    return base + 1, base + last_day


def copy_statement(table: str, source: str, iam_role: str = "default") -> str:
    role = "default" if iam_role == "default" else _literal(iam_role)
    return f"COPY {table} FROM {_literal(source)} IAM_ROLE {role} FORMAT AS PARQUET"


def month_load(
    warehouse_uri: str, month: Month, *, schema: str = "taxi", iam_role: str = "default"
) -> list[str]:
    """Statements that load ``month`` from ``warehouse_uri``, e.g. ``s3://lake/warehouse/yellow``.

    ``iam_role="default"`` uses the namespace's default role (the Terraform warehouse
    module sets it to the COPY role); pass an ARN to use another.
    """
    if not warehouse_uri.startswith("s3://"):
        raise ValueError(f"COPY reads from S3; got {warehouse_uri!r}")
    root = warehouse_uri.rstrip("/")
    schema = _identifier(schema)

    statements: list[str] = []
    for dim in DIMENSIONS:
        table = f"{schema}.{dim}"
        statements.append(f"DELETE FROM {table}")
        statements.append(copy_statement(table, f"{root}/{dim}/", iam_role))

    first, last = date_key_range(month)
    facts = f"{schema}.{FACT}"
    statements.append(f"DELETE FROM {facts} WHERE pickup_date_key BETWEEN {first} AND {last}")
    # An S3 prefix, not a folder: it matches every pickup_date=YYYY-MM-DD/ of the month.
    statements.append(copy_statement(facts, f"{root}/{FACT}/pickup_date={month.key}-", iam_role))
    return statements
