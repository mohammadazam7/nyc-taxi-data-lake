from __future__ import annotations

import os
from collections.abc import Sequence

import pytest

from nyc_taxi_lake.glue_entry import parse, run

# What Glue passes: its own arguments mixed in with the job's defaults and the run's.
GLUE_ARGV = [
    "--JOB_ID", "j_123",
    "--JOB_RUN_ID", "jr_456",
    "--job-bookmark-option", "job-bookmark-disable",
    "--TempDir", "s3://nyc-lake-artifacts/glue-temp/",
    "--enable-metrics", "true",
    "--JOB_NAME", "nyc-lake-clean",
    "--lake-root", "s3://nyc-lake-lake",
    "--taxi-type", "yellow",
]  # fmt: skip


def test_clean_run_maps_to_cli_and_env() -> None:
    job = parse([*GLUE_ARGV, "--stage", "clean", "--start", "2024-01", "--end", "2024-03"])

    assert job.env == {"NYC_LAKE_ROOT": "s3://nyc-lake-lake", "NYC_LAKE_TAXI_TYPE": "yellow"}
    assert job.argv == ["clean", "2024-01", "2024-03", "--master", ""]


def test_end_defaults_to_start() -> None:
    job = parse([*GLUE_ARGV, "--stage", "model", "--start", "2024-02"])

    assert job.argv[:3] == ["model", "2024-02", "2024-02"]


def test_quality_passes_the_alert_sink() -> None:
    arn = "arn:aws:sns:us-east-1:123456789012:nyc-lake-alerts"
    sink = ["--alert-sink", "sns", "--sns-topic-arn", arn]
    job = parse([*GLUE_ARGV, "--stage", "quality", "--start", "2024-01", *sink])

    assert job.argv[-4:] == ["--alert-sink", "sns", "--sns-topic-arn", arn]


def test_alert_arguments_only_go_to_quality() -> None:
    job = parse([*GLUE_ARGV, "--stage", "clean", "--start", "2024-01", "--alert-sink", "sns"])

    assert "--alert-sink" not in job.argv


@pytest.mark.parametrize(
    "missing", [["--stage", "clean"], ["--start", "2024-01"]], ids=["no-start", "no-stage"]
)
def test_required_arguments(missing: list[str]) -> None:
    with pytest.raises(SystemExit):
        parse([*GLUE_ARGV, *missing])


def test_unknown_stage_is_rejected() -> None:
    with pytest.raises(SystemExit):
        parse([*GLUE_ARGV, "--stage", "ingest", "--start", "2024-01"])


def test_run_sets_env_and_returns_the_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NYC_LAKE_ROOT", raising=False)
    monkeypatch.delenv("NYC_LAKE_TAXI_TYPE", raising=False)
    seen: dict[str, object] = {}

    def fake_main(argv: Sequence[str] | None) -> int:
        seen["argv"] = argv
        seen["root"] = os.environ["NYC_LAKE_ROOT"]
        return 1

    code = run([*GLUE_ARGV, "--stage", "quality", "--start", "2024-01"], main=fake_main)

    assert code == 1
    assert seen["root"] == "s3://nyc-lake-lake"
    assert seen["argv"] == ["quality", "2024-01", "2024-01", "--master", "", "--alert-sink", "log"]
