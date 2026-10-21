from __future__ import annotations

from typing import Any

import pytest

from nyc_taxi_lake.load.redshift import DataApiRunner, LoadError


class FakeDataApi:
    def __init__(self, states: list[str], error: str | None = None) -> None:
        self.states = states
        self.error = error
        self.batches: list[dict[str, Any]] = []
        self.cancelled: list[str] = []

    def batch_execute_statement(self, **kwargs: Any) -> dict[str, Any]:
        self.batches.append(kwargs)
        return {"Id": "stmt-1"}

    def describe_statement(self, Id: str) -> dict[str, Any]:
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        out: dict[str, Any] = {"Id": Id, "Status": state}
        if self.error and state == "FAILED":
            out["Error"] = self.error
        return out

    def cancel_statement(self, Id: str) -> dict[str, Any]:
        self.cancelled.append(Id)
        return {"Status": True}


def _runner(api: FakeDataApi, **kwargs: Any) -> DataApiRunner:
    return DataApiRunner("wg", "taxi", client=api, sleep=lambda _: None, **kwargs)


def test_submits_one_batch_and_waits_for_it() -> None:
    api = FakeDataApi(["SUBMITTED", "STARTED", "FINISHED"])
    assert _runner(api).run(["DELETE FROM t", "COPY t FROM 's3://x/'"]) == "stmt-1"
    assert api.batches == [
        {
            "WorkgroupName": "wg",
            "Database": "taxi",
            "Sqls": ["DELETE FROM t", "COPY t FROM 's3://x/'"],
        }
    ]
    assert api.states == ["FINISHED"]


def test_a_failed_batch_raises_with_redshifts_error() -> None:
    api = FakeDataApi(["STARTED", "FAILED"], error="S3ServiceException: Access Denied")
    with pytest.raises(LoadError, match="Access Denied"):
        _runner(api).run(["COPY t FROM 's3://x/'"])


def test_an_aborted_batch_raises() -> None:
    with pytest.raises(LoadError, match="ABORTED"):
        _runner(FakeDataApi(["ABORTED"])).run(["SELECT 1"])


def test_a_batch_past_the_timeout_is_cancelled() -> None:
    api = FakeDataApi(["STARTED"])
    ticks = iter(range(100))
    runner = _runner(api, timeout_seconds=5, clock=lambda: float(next(ticks)))
    with pytest.raises(LoadError, match="still STARTED"):
        runner.run(["SELECT 1"])
    assert api.cancelled == ["stmt-1"]


def test_refuses_an_empty_batch() -> None:
    with pytest.raises(ValueError):
        _runner(FakeDataApi(["FINISHED"])).run([])
