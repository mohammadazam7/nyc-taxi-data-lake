"""Check results and the per-run JSON report."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class Status(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True)
class CheckResult:
    name: str
    kind: str
    severity: str
    passed: bool
    observed: float | int | None
    threshold: str
    detail: str = ""

    @property
    def status(self) -> Status:
        if self.passed:
            return Status.PASS
        return Status.FAIL if self.severity == "error" else Status.WARN


@dataclass(frozen=True)
class QualityReport:
    month: str
    taxi_type: str
    run_at: str
    results: list[CheckResult] = field(default_factory=list)

    @property
    def status(self) -> Status:
        statuses = {r.status for r in self.results}
        if Status.FAIL in statuses:
            return Status.FAIL
        if Status.WARN in statuses:
            return Status.WARN
        return Status.PASS

    @property
    def breaches(self) -> list[CheckResult]:
        return [r for r in self.results if not r.passed]

    def to_dict(self) -> dict[str, Any]:
        counts = {s.value: 0 for s in Status}
        for r in self.results:
            counts[r.status.value] += 1
        return {
            "month": self.month,
            "taxi_type": self.taxi_type,
            "run_at": self.run_at,
            "status": self.status.value,
            "counts": counts,
            "results": [{**asdict(r), "status": r.status.value} for r in self.results],
        }

    def write(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.month}.json"
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n")
        return path
