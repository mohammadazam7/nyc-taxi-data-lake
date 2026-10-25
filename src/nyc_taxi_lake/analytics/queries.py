"""The analytics queries over the star schema.

Each query is a ``.sql`` file in this package. The files are written in the subset of SQL
that Spark SQL, Redshift and Athena share, so one text serves the local warehouse zone
and the AWS warehouse:

* tables are unqualified (``fact_trips``, not ``taxi.fact_trips``); the runner decides
  where they resolve, through temporary views in Spark or ``search_path`` in Redshift;
* the month range is bound through the named parameters ``:start_key`` and ``:end_key``
  (``yyyymmdd`` date keys, inclusive), which both Spark and the Redshift Data API accept,
  so no value is ever formatted into the SQL text;
* filters use ``pickup_date_key`` rather than the ``pickup_date`` partition column,
  because the Redshift table has no ``pickup_date``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from importlib import resources

from nyc_taxi_lake.months import Month

# Order is the order the dashboard shows them in.
QUERY_NAMES = (
    "monthly_revenue",
    "daily_trips",
    "hourly_demand",
    "busiest_pickup_zones",
    "payment_mix",
)

PARAMETERS = ("start_key", "end_key")


@dataclass(frozen=True)
class Query:
    name: str
    sql: str

    @property
    def description(self) -> str:
        """The leading ``--`` comment block, joined into one line."""
        lines = []
        for line in self.sql.splitlines():
            if not line.startswith("--"):
                break
            lines.append(line.removeprefix("--").strip())
        return " ".join(lines)


def load_query(name: str) -> Query:
    if name not in QUERY_NAMES:
        raise ValueError(f"unknown analytics query {name!r}; expected one of {QUERY_NAMES}")
    text = resources.files(__package__).joinpath("sql", f"{name}.sql").read_text("utf-8")
    return Query(name=name, sql=text.strip())


def load_queries() -> list[Query]:
    return [load_query(name) for name in QUERY_NAMES]


def date_key(day: date) -> int:
    """The ``yyyymmdd`` integer that ``dim_date.date_key`` uses."""
    return day.year * 10_000 + day.month * 100 + day.day


def month_bounds(start: Month, end: Month) -> dict[str, int]:
    """Parameters covering every day from the first of ``start`` to the last of ``end``."""
    if end < start:
        raise ValueError(f"end month {end.key} is before start month {start.key}")
    after = end.next()
    last = date.fromordinal(date(after.year, after.month, 1).toordinal() - 1)
    return {
        "start_key": date_key(date(start.year, start.month, 1)),
        "end_key": date_key(last),
    }
