from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nyc_taxi_lake.quality.report import CheckResult, QualityReport, Status
from nyc_taxi_lake.quality.spec import (
    Freshness,
    NullRate,
    ReferentialIntegrity,
    RowCountReconciles,
    SpecError,
    ValueRange,
    load_suite,
    parse_check,
    parse_suite,
)


def test_default_suite_loads_and_covers_every_kind() -> None:
    suite = load_suite()
    kinds = {type(c) for c in suite}
    assert {RowCountReconciles, NullRate, ValueRange, ReferentialIntegrity, Freshness} <= kinds
    assert len({c.name for c in suite}) == len(suite)


def test_defaults_name_and_severity() -> None:
    check = parse_check({"kind": "null_rate", "table": "fact_trips", "column": "x", "max": 0}, 0)
    assert check == NullRate("null_rate:fact_trips.x", "error", "fact_trips", "x", 0.0)


def test_range_fills_optional_keys() -> None:
    check = parse_check({"kind": "range", "table": "clean", "column": "fare_amount", "min": 0}, 0)
    assert isinstance(check, ValueRange)
    assert (check.min, check.max, check.max_violation_rate) == (0, None, 0.0)


def test_references_split_into_dimension_and_key() -> None:
    check = parse_check(
        {
            "kind": "referential_integrity",
            "table": "fact_trips",
            "column": "vendor_key",
            "references": "dim_vendor.vendor_key",
        },
        0,
    )
    assert isinstance(check, ReferentialIntegrity)
    assert (check.dimension, check.key) == ("dim_vendor", "vendor_key")


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        ({"kind": "nope"}, "unknown kind"),
        ({"kind": "null_rate", "table": "fact_trips", "column": "x"}, "missing max"),
        (
            {"kind": "null_rate", "table": "fact_trips", "column": "x", "max": 0, "maxx": 1},
            "unexpected maxx",
        ),
        ({"kind": "null_rate", "table": "facts", "column": "x", "max": 0}, "unknown table"),
        ({"kind": "null_rate", "table": "clean", "column": "x", "max": 5}, "between 0 and 1"),
        ({"kind": "quarantine_rate", "max": 0.1, "severity": "fatal"}, "severity"),
        ({"kind": "row_count", "source": "clean", "target": "raw"}, "row_count supports"),
        ({"kind": "range", "table": "clean", "column": "x"}, "min, max or both"),
        ({"kind": "range", "table": "clean", "column": "x", "min": 2, "max": 1}, "greater"),
        (
            {
                "kind": "referential_integrity",
                "table": "fact_trips",
                "column": "x",
                "references": "dim_zone",
            },
            "references must be",
        ),
        (
            {"kind": "freshness", "table": "clean", "column": "x", "max_gap_hours": -1},
            "negative",
        ),
    ],
)
def test_malformed_checks_are_rejected(entry: dict[str, Any], message: str) -> None:
    with pytest.raises(SpecError, match=message):
        parse_check(entry, 0)


def test_suite_rejects_empty_and_duplicate_names() -> None:
    with pytest.raises(SpecError, match="at least one"):
        parse_suite({})
    twice = {"kind": "quarantine_rate", "max": 0.1}
    with pytest.raises(SpecError, match="repeated: quarantine_rate"):
        parse_suite({"check": [twice, twice]})


def test_load_suite_reports_toml_errors(tmp_path: Path) -> None:
    bad = tmp_path / "suite.toml"
    bad.write_text("[[check]\nkind=")
    with pytest.raises(SpecError, match=r"suite\.toml"):
        load_suite(bad)


def _result(name: str, passed: bool, severity: str = "error") -> CheckResult:
    return CheckResult(name, "null_rate", severity, passed, 0.0, "<= 0")


def test_report_status_is_the_worst_result() -> None:
    report = QualityReport("2024-01", "yellow", "t", [_result("a", True)])
    assert report.status is Status.PASS
    report.results.append(_result("b", False, "warn"))
    assert report.status is Status.WARN
    report.results.append(_result("c", False))
    assert report.status is Status.FAIL
    assert [r.name for r in report.breaches] == ["b", "c"]


def test_report_writes_json_with_counts(tmp_path: Path) -> None:
    report = QualityReport(
        "2024-01", "yellow", "2024-02-03T00:00:00+00:00", [_result("a", True), _result("b", False)]
    )
    saved = json.loads(report.write(tmp_path / "reports").read_text())
    assert saved["status"] == "fail"
    assert saved["counts"] == {"pass": 1, "warn": 0, "fail": 1}
    assert saved["results"][1]["name"] == "b"
    assert saved["results"][1]["status"] == "fail"
