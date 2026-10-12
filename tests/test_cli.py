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
