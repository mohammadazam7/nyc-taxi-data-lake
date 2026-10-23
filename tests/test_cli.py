from __future__ import annotations

from pathlib import Path

import pytest

from nyc_taxi_lake.cli import build_parser, main


def test_clean_parser_defaults_to_local_master() -> None:
    args = build_parser().parse_args(["clean", "2024-01", "2024-02"])
    assert (args.command, args.start, args.end, args.master) == (
        "clean",
        "2024-01",
        "2024-02",
        "local[*]",
    )


def test_ingest_sample_prints_one_line_per_month(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NYC_LAKE_ROOT", str(tmp_path))
    assert main(["ingest", "2024-01", "2024-02", "--sample", "--sample-rows", "500"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [line.split()[0] for line in lines] == ["2024-01", "2024-02"]
    assert all("landed" in line for line in lines)


@pytest.mark.spark
def test_clean_after_ingest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pytest.importorskip("pyspark", reason="install the [spark] extra to run Spark tests")
    monkeypatch.setenv("NYC_LAKE_ROOT", str(tmp_path))
    main(["ingest", "2024-01", "--sample", "--sample-rows", "1000"])
    capsys.readouterr()

    assert main(["clean", "2024-01", "--master", "local[2]"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("2024-01")
    assert "quarantined" in out
    assert any((tmp_path / "clean" / "yellow").glob("pickup_date=2024-01-*"))
    assert (tmp_path / "clean" / "_runs" / "yellow" / "2024-01.json").exists()


@pytest.mark.spark
def test_model_after_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pytest.importorskip("pyspark", reason="install the [spark] extra to run Spark tests")
    monkeypatch.setenv("NYC_LAKE_ROOT", str(tmp_path))
    main(["ingest", "2024-01", "--sample", "--sample-rows", "1000"])
    main(["clean", "2024-01", "--master", "local[2]"])
    capsys.readouterr()

    assert main(["model", "2024-01", "--sample-zones", "--master", "local[2]"]) == 0
    out = capsys.readouterr().out
    assert "placeholder zone lookup" in out
    assert "fact rows" in out
    assert any((tmp_path / "warehouse" / "yellow" / "fact_trips").glob("pickup_date=2024-01-*"))


def test_load_dry_run_prints_one_transaction_per_month(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NYC_LAKE_ROOT", "s3://lake")
    assert main(["load", "2024-01", "2024-02", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert out.count("-- 2024-") == 2
    assert (
        "COPY taxi.fact_trips FROM 's3://lake/warehouse/yellow/fact_trips/pickup_date=2024-02-'"
        in out
    )
    assert "pickup_date_key BETWEEN 20240201 AND 20240229" in out


def test_load_refuses_a_local_lake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NYC_LAKE_ROOT", str(tmp_path))
    with pytest.raises(ValueError, match="COPY reads from S3"):
        main(["load", "2024-01", "--dry-run"])


def test_load_needs_a_workgroup(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NYC_LAKE_ROOT", "s3://lake")
    monkeypatch.delenv("NYC_LAKE_REDSHIFT_WORKGROUP", raising=False)
    assert main(["load", "2024-01"]) == 2
    assert "--workgroup" in capsys.readouterr().out


def test_load_runs_each_month_through_the_data_api(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nyc_taxi_lake.load import redshift

    submitted: list[tuple[str, str, int]] = []

    def fake_run(self: redshift.DataApiRunner, statements: list[str]) -> str:
        submitted.append((self.workgroup, self.database, len(statements)))
        return f"stmt-{len(submitted)}"

    monkeypatch.setattr(redshift.DataApiRunner, "run", fake_run)
    monkeypatch.setenv("NYC_LAKE_ROOT", "s3://lake")
    assert main(["load", "2024-01", "2024-02", "--workgroup", "wg"]) == 0
    assert submitted == [("wg", "taxi", 12), ("wg", "taxi", 12)]
    assert "stmt-2" in capsys.readouterr().out


def test_run_rejects_unknown_stages(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["run", "2024-01", "--stages", "ingest,deploy"])
    assert "unknown stage(s): deploy" in capsys.readouterr().err


def test_run_ingest_stage_over_a_range(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NYC_LAKE_ROOT", str(tmp_path))
    argv = ["run", "2024-01", "2024-02", "--stages", "ingest", "--sample", "--sample-rows", "300"]
    assert main(argv) == 0
    assert [line.split()[0] for line in capsys.readouterr().out.splitlines()] == [
        "2024-01",
        "2024-02",
    ]


def test_backfill_ingest_stage_one_month_at_a_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NYC_LAKE_ROOT", str(tmp_path))
    argv = ["backfill", "2024-01", "2024-03", "--stages", "ingest", "--sample"]
    assert main([*argv, "--sample-rows", "300"]) == 0
    out = capsys.readouterr().out
    assert out.count("landed") == 3
    assert "backfill: 3 done, 0 skipped" in out


@pytest.mark.spark
def test_run_end_to_end_then_backfill_resumes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pytest.importorskip("pyspark", reason="install the [spark] extra to run Spark tests")
    monkeypatch.setenv("NYC_LAKE_ROOT", str(tmp_path))
    common = ["--sample", "--sample-rows", "1000", "--sample-zones", "--master", "local[2]"]

    assert main(["run", "2024-01", *common]) == 0
    assert (tmp_path / "quality" / "yellow" / "2024-01.json").exists()
    capsys.readouterr()

    # 2024-01 passed in the run above, so the backfill only processes 2024-02.
    assert main(["backfill", "2024-01", "2024-02", *common]) == 0
    assert "backfill: 1 done, 1 skipped" in capsys.readouterr().out
    assert (tmp_path / "quality" / "yellow" / "2024-02.json").exists()
