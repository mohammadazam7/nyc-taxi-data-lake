import pytest

from nyc_taxi_lake.months import Month, month_range


def test_parse_and_partition() -> None:
    m = Month.parse("2024-03")
    assert m.key == "2024-03"
    assert m.partition == "year=2024/month=03"


def test_range_crosses_year_boundary() -> None:
    keys = [m.key for m in month_range("2023-11", "2024-02")]
    assert keys == ["2023-11", "2023-12", "2024-01", "2024-02"]


@pytest.mark.parametrize("bad", ["2024-13", "24-01", "2024/01", "2008-12"])
def test_rejects_invalid_months(bad: str) -> None:
    with pytest.raises(ValueError):
        Month.parse(bad)


def test_range_rejects_reversed_bounds() -> None:
    with pytest.raises(ValueError):
        month_range("2024-05", "2024-01")
