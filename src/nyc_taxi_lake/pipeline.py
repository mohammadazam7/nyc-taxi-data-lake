"""Run the pipeline's stages in order for a range of months.

Each stage is an ``nyc-lake`` subcommand. This module only decides which commands to
run, with which arguments and in which order, and stops at the first one that exits
non-zero. Two orders are supported:

* :func:`run_stages` is stage-major: every month goes through ``ingest``, then every
  month through ``clean``, and so on. Each Spark stage starts one session for the whole
  range, which is the cheaper order for a scheduled run of one or two months.
* :func:`backfill` is month-major: one month goes through every stage before the next
  month starts. A month whose quality report already passed is skipped, so a backfill
  that stops part way can be re-run with the same arguments and picks up where it
  stopped.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from nyc_taxi_lake.config import Settings
from nyc_taxi_lake.months import Month, month_range

STAGES = ("ingest", "clean", "model", "quality", "load")
DEFAULT_STAGES = ("ingest", "clean", "model", "quality")

Main = Callable[[Sequence[str] | None], int]


@dataclass(frozen=True)
class RunOptions:
    """Arguments passed through to the stage commands."""

    master: str = "local[*]"
    sample: bool = False
    sample_rows: int = 50_000
    sample_zones: bool = False
    load_dry_run: bool = False


@dataclass(frozen=True)
class StepResult:
    stage: str
    start: str
    end: str
    exit_code: int

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


def parse_stages(value: str) -> tuple[str, ...]:
    """Parse ``"clean,model"`` into stages, in pipeline order and without duplicates."""
    names = {s.strip() for s in value.split(",") if s.strip()}
    unknown = sorted(names - set(STAGES))
    if unknown:
        raise ValueError(f"unknown stage(s): {', '.join(unknown)}; expected {', '.join(STAGES)}")
    if not names:
        raise ValueError("no stages given")
    return tuple(s for s in STAGES if s in names)


def stage_argv(stage: str, start: Month, end: Month, options: RunOptions) -> list[str]:
    """The ``nyc-lake`` argv that runs one stage over a month range."""
    argv = [stage, start.key, end.key]
    if stage == "ingest":
        if options.sample:
            argv += ["--sample", "--sample-rows", str(options.sample_rows)]
    elif stage in ("clean", "model", "quality"):
        argv += ["--master", options.master]
        if stage == "model" and options.sample_zones:
            argv.append("--sample-zones")
    elif stage == "load":
        if options.load_dry_run:
            argv.append("--dry-run")
    else:
        raise ValueError(f"unknown stage: {stage}")
    return argv


def run_stages(
    months: Sequence[Month],
    stages: Sequence[str],
    options: RunOptions,
    main: Main,
) -> list[StepResult]:
    """Run each stage over all ``months``; stop after the first stage that fails."""
    if not months:
        return []
    start, end = min(months), max(months)
    results: list[StepResult] = []
    for stage in stages:
        code = main(stage_argv(stage, start, end, options))
        results.append(StepResult(stage, start.key, end.key, code))
        if code != 0:
            break
    return results


def month_passed(settings: Settings, month: Month) -> bool:
    """True if the month's quality report exists and did not fail.

    A report with warnings counts as passed: warnings are reported but do not block
    the load, matching ``nyc-lake quality``'s default ``--fail-on error``.
    """
    report = settings.quality_root / settings.taxi_type / f"{month.key}.json"
    if not report.exists():
        return False
    try:
        status = json.loads(report.read_text()).get("status")
    except (json.JSONDecodeError, AttributeError):
        return False
    return status in ("pass", "warn")


@dataclass(frozen=True)
class BackfillResult:
    done: list[str]
    skipped: list[str]
    failed: StepResult | None

    @property
    def ok(self) -> bool:
        return self.failed is None


def backfill(
    start: str,
    end: str,
    stages: Sequence[str],
    options: RunOptions,
    settings: Settings,
    main: Main,
    *,
    force: bool = False,
) -> BackfillResult:
    """Run every stage for one month at a time, oldest first.

    Months that already have a passing quality report are skipped unless ``force`` is
    set. The first failing stage stops the backfill; months before it stay complete.
    """
    done: list[str] = []
    skipped: list[str] = []
    for month in month_range(start, end):
        if not force and month_passed(settings, month):
            skipped.append(month.key)
            continue
        steps = run_stages([month], stages, options, main)
        failure = next((s for s in steps if not s.ok), None)
        if failure is not None:
            return BackfillResult(done, skipped, failure)
        done.append(month.key)
    return BackfillResult(done, skipped, None)
