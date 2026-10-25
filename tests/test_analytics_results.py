from datetime import date, datetime
from decimal import Decimal

import pytest

from nyc_taxi_lake.analytics.results import QueryResult, to_scalar


def test_driver_values_become_json_scalars() -> None:
    assert to_scalar(Decimal("1025048.02")) == 1025048.02
    assert to_scalar(date(2024, 1, 5)) == "2024-01-05"
    assert to_scalar(datetime(2024, 1, 5, 7, 30)) == "2024-01-05T07:30:00"
    assert to_scalar(None) is None
    assert to_scalar(7) == 7


def test_unsupported_values_are_rejected() -> None:
    with pytest.raises(TypeError, match="bytes"):
        to_scalar(b"\x00")


def test_rows_must_match_the_columns() -> None:
    with pytest.raises(ValueError, match="expected 2"):
        QueryResult.from_records("q", ["a", "b"], [(1, 2, 3)])


def test_round_trips_through_json_shape() -> None:
    result = QueryResult.from_records(
        "daily_trips",
        ["calendar_date", "trips", "revenue"],
        [(date(2024, 1, 1), 10, Decimal("201.50")), (date(2024, 1, 2), 12, Decimal("240.00"))],
    )
    assert result.column("trips") == [10, 12]
    assert result.records()[0] == {"calendar_date": "2024-01-01", "trips": 10, "revenue": 201.5}
    assert QueryResult.from_dict(result.to_dict()) == result
