import re
from datetime import date

import pytest

from nyc_taxi_lake.analytics.queries import (
    PARAMETERS,
    QUERY_NAMES,
    date_key,
    load_queries,
    load_query,
    month_bounds,
)
from nyc_taxi_lake.months import Month

STAR_TABLES = {
    "fact_trips",
    "dim_date",
    "dim_zone",
    "dim_vendor",
    "dim_rate_code",
    "dim_payment_type",
}


def test_every_query_loads_with_a_description() -> None:
    queries = load_queries()
    assert [q.name for q in queries] == list(QUERY_NAMES)
    for query in queries:
        assert query.sql.lstrip().startswith("--")
        assert query.description
        assert "SELECT" in query.sql


@pytest.mark.parametrize("name", QUERY_NAMES)
def test_queries_bind_the_month_range_as_parameters(name: str) -> None:
    sql = load_query(name).sql
    assert set(re.findall(r":(\w+)", sql)) == set(PARAMETERS)
    assert "pickup_date_key BETWEEN :start_key AND :end_key" in sql


@pytest.mark.parametrize("name", QUERY_NAMES)
def test_queries_use_unqualified_star_tables_only(name: str) -> None:
    sql = load_query(name).sql
    # Every table reference is aliased; EXTRACT(... FROM column) is not a table.
    tables = set(re.findall(r"\b(?:FROM|JOIN)\s+([\w.]+)\s+AS\b", sql))
    assert "fact_trips" in tables
    assert tables <= STAR_TABLES
    assert "taxi." not in sql
    # pickup_date is a lake partition directory, not a Redshift column.
    assert not re.search(r"\bpickup_date\b", sql)


def test_unknown_query_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown analytics query"):
        load_query("drop_everything")


def test_date_key_matches_the_dimension_format() -> None:
    assert date_key(date(2024, 1, 5)) == 20240105


def test_month_bounds_cover_whole_months() -> None:
    assert month_bounds(Month(2024, 1), Month(2024, 2)) == {
        "start_key": 20240101,
        "end_key": 20240229,
    }
    assert month_bounds(Month(2023, 12), Month(2023, 12))["end_key"] == 20231231


def test_month_bounds_reject_a_reversed_range() -> None:
    with pytest.raises(ValueError, match="before start"):
        month_bounds(Month(2024, 3), Month(2024, 1))
