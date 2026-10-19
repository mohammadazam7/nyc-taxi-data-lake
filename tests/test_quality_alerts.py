from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from nyc_taxi_lake.quality.alerts import LogSink, SnsSink, make_sink, subject
from nyc_taxi_lake.quality.report import CheckResult, QualityReport

ARN = "arn:aws:sns:us-east-1:123456789012:nyc-lake-alerts"


def _report(*failures: str, warn: bool = False) -> QualityReport:
    results = [CheckResult("ok", "null_rate", "error", True, 0.0, "<= 0.00%")]
    for name in failures:
        severity = "warn" if warn else "error"
        results.append(
            CheckResult(name, "range", severity, False, 0.2, "<= 0.10%", "20 of 100 outside")
        )
    return QualityReport("2024-01", "yellow", "2024-02-03T00:00:00+00:00", results)


class FakeSns:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def publish(self, **kwargs: Any) -> dict[str, str]:
        self.calls.append(kwargs)
        return {"MessageId": "1"}


def test_subject_names_status_month_and_breach_count() -> None:
    assert subject(_report("a")) == "[nyc-lake] FAIL: yellow 2024-01, 1 check breached"
    assert subject(_report("a", "b", warn=True)).endswith("WARN: yellow 2024-01, 2 checks breached")


def test_log_sink_uses_error_level_for_failures(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        LogSink().send(_report("fare_range"))
    assert [r.levelno for r in caplog.records] == [logging.ERROR, logging.ERROR]
    assert "fare_range: observed 0.2, expected <= 0.10% (20 of 100 outside)" in caplog.text


def test_log_sink_uses_warning_level_for_warnings(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        LogSink().send(_report("x", warn=True))
    assert {r.levelno for r in caplog.records} == {logging.WARNING}


def test_sns_sink_publishes_summary_json_and_filterable_attributes() -> None:
    sns = FakeSns()
    SnsSink(ARN, client=sns).send(_report("fare_range"))

    (call,) = sns.calls
    assert call["TopicArn"] == ARN
    assert call["Subject"] == subject(_report("fare_range"))
    assert call["MessageAttributes"]["status"] == {"DataType": "String", "StringValue": "fail"}
    body, payload = call["Message"].split("breaches:\n", 1)
    assert "fare_range" in body
    assert [b["name"] for b in json.loads(payload)] == ["fare_range"]


def test_sns_message_is_truncated_before_the_sns_limit() -> None:
    message = SnsSink(ARN, client=FakeSns()).message(_report(*[f"c{i}" * 400 for i in range(400)]))
    assert len(message.encode()) < 256 * 1024
    assert "breaches:" not in message
    assert "more\n\nTruncated to fit SNS" in message


def test_make_sink_validates_its_arguments() -> None:
    assert isinstance(make_sink("log"), LogSink)
    assert isinstance(make_sink("sns", ARN), SnsSink)
    with pytest.raises(ValueError, match="topic ARN"):
        make_sink("sns")
    with pytest.raises(ValueError, match="expected an SNS topic ARN"):
        SnsSink("nyc-lake-alerts")
    with pytest.raises(ValueError, match="unknown alert sink"):
        make_sink("pagerduty")
