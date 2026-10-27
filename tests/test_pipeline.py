from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from nyc_taxi_lake.config import Settings
from nyc_taxi_lake.months import Month, month_range
from nyc_taxi_lake.pipeline import (
    DEFAULT_STAGES,
    RunOptions,
    StepResult,
    backfill,
    month_passed,
    parse_stages,
    run_stages,
    stage_argv,
    timings,
)


class FakeMain:
    """Records each argv and fails the calls whose (stage, start) is in ``fail``."""

    def __init__(self, fail: set[tuple[str, str]] | None = None) -> None:
        self.calls: list[list[str]] = []
        self.fail = fail or set()

    def __call__(self, argv: Sequence[str] | None) -> int:
        assert argv is not None
        self.calls.append(list(argv))
        return 1 if (argv[0], argv[1]) in self.fail else 0


def _settings(root: Path) -> Settings:
    return Settings(
        lake_root=root,
        tlc_base_url="https://example.invalid",
        taxi_type="yellow",
        http_timeout_s=1,
        http_retries=0,
    )


def _report(root: Path, month: str, status: str) -> None:
    directory = root / "quality" / "yellow"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{month}.json").write_text(json.dumps({"status": status}))


def test_parse_stages_orders_and_deduplicates() -> None:
    assert parse_stages("quality, clean,clean") == ("clean", "quality")


@pytest.mark.parametrize("value", ["", " , ", "clean,deploy"])
def test_parse_stages_rejects_unknown_or_empty(value: str) -> None:
    with pytest.raises(ValueError):
        parse_stages(value)


def test_stage_argv_passes_each_stage_its_own_options() -> None:
    jan, mar = Month(2024, 1), Month(2024, 3)
    opts = RunOptions(master="local[2]", sample=True, sample_rows=10, sample_zones=True)
    assert stage_argv("ingest", jan, mar, opts) == [
        "ingest",
        "2024-01",
        "2024-03",
        "--sample",
        "--sample-rows",
        "10",
    ]
    assert stage_argv("clean", jan, mar, opts) == [
        "clean",
        "2024-01",
        "2024-03",
        "--master",
        "local[2]",
    ]
    assert stage_argv("model", jan, mar, opts)[-1] == "--sample-zones"
    assert stage_argv("load", jan, mar, RunOptions(load_dry_run=True))[-1] == "--dry-run"


def test_stage_argv_downloads_unless_sampling() -> None:
    assert stage_argv("ingest", Month(2024, 1), Month(2024, 1), RunOptions()) == [
        "ingest",
        "2024-01",
        "2024-01",
    ]


def test_run_stages_runs_each_stage_once_over_the_whole_range() -> None:
    main = FakeMain()
    results = run_stages(month_range("2024-01", "2024-03"), DEFAULT_STAGES, RunOptions(), main)
    assert [c[:3] for c in main.calls] == [
        [stage, "2024-01", "2024-03"] for stage in DEFAULT_STAGES
    ]
    assert all(r.ok for r in results)


def test_run_stages_stops_at_the_first_failure() -> None:
    main = FakeMain(fail={("clean", "2024-01")})
    results = run_stages([Month(2024, 1)], DEFAULT_STAGES, RunOptions(), main)
    assert [r.stage for r in results] == ["ingest", "clean"]
    assert not results[-1].ok
    assert len(main.calls) == 2


def test_run_stages_times_each_stage_with_the_given_clock() -> None:
    ticks = iter([0.0, 2.5, 2.5, 10.0])
    results = run_stages(
        [Month(2024, 1)], ("ingest", "clean"), RunOptions(), FakeMain(), clock=lambda: next(ticks)
    )
    assert [r.seconds for r in results] == [2.5, 7.5]


def test_timings_summarises_a_failed_run() -> None:
    results = [
        StepResult("ingest", "2024-01", "2024-01", 0, 1.25),
        StepResult("clean", "2024-01", "2024-01", 1, 3.5),
    ]
    body = timings(results)
    assert body["ok"] is False
    assert body["total_seconds"] == 4.75
    stages = body["stages"]
    assert isinstance(stages, list)
    assert [s["exit_code"] for s in stages] == [0, 1]


def test_month_passed_reads_the_quality_report(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    assert not month_passed(settings, Month(2024, 1))
    _report(tmp_path, "2024-01", "warn")
    _report(tmp_path, "2024-02", "fail")
    (tmp_path / "quality" / "yellow" / "2024-03.json").write_text("not json")
    assert month_passed(settings, Month(2024, 1))
    assert not month_passed(settings, Month(2024, 2))
    assert not month_passed(settings, Month(2024, 3))


def test_backfill_runs_months_one_at_a_time_and_skips_passed_ones(tmp_path: Path) -> None:
    _report(tmp_path, "2024-02", "pass")
    main = FakeMain()
    result = backfill(
        "2024-01", "2024-03", ("clean", "model"), RunOptions(), _settings(tmp_path), main
    )
    assert result.ok
    assert result.done == ["2024-01", "2024-03"]
    assert result.skipped == ["2024-02"]
    assert [c[:2] for c in main.calls] == [
        ["clean", "2024-01"],
        ["model", "2024-01"],
        ["clean", "2024-03"],
        ["model", "2024-03"],
    ]


def test_backfill_force_reruns_passed_months(tmp_path: Path) -> None:
    _report(tmp_path, "2024-01", "pass")
    main = FakeMain()
    result = backfill(
        "2024-01", "2024-01", ("clean",), RunOptions(), _settings(tmp_path), main, force=True
    )
    assert result.done == ["2024-01"]
    assert result.skipped == []


def test_backfill_stops_at_the_failing_month(tmp_path: Path) -> None:
    main = FakeMain(fail={("model", "2024-02")})
    result = backfill(
        "2024-01", "2024-04", ("clean", "model"), RunOptions(), _settings(tmp_path), main
    )
    assert not result.ok
    assert result.done == ["2024-01"]
    assert result.failed is not None
    assert (result.failed.stage, result.failed.start) == ("model", "2024-02")
    assert ["clean", "2024-03"] not in [c[:2] for c in main.calls]
