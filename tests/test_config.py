from __future__ import annotations

from pathlib import Path

import pytest

from nyc_taxi_lake.cli import main
from nyc_taxi_lake.config import Settings
from nyc_taxi_lake.ingest.raw_zone import partition_dir
from nyc_taxi_lake.months import Month
from nyc_taxi_lake.paths import S3Path


def test_local_root_is_made_absolute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("NYC_LAKE_ROOT", raising=False)
    settings = Settings.from_env()
    assert settings.lake_root == tmp_path / "lake"
    assert settings.clean_root == tmp_path / "lake" / "clean"


def test_s3_root_gives_s3_zone_uris(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NYC_LAKE_ROOT", "s3://nyc-lake-dev-lake")
    settings = Settings.from_env()
    assert isinstance(settings.lake_root, S3Path)
    # These strings are what the Spark jobs read and write.
    assert str(settings.clean_root / "yellow") == "s3://nyc-lake-dev-lake/clean/yellow"
    assert str(partition_dir(settings.raw_root, "yellow", Month(2024, 1))) == (
        "s3://nyc-lake-dev-lake/raw/yellow/year=2024/month=01"
    )


def test_ingest_refuses_an_s3_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NYC_LAKE_ROOT", "s3://nyc-lake-dev-lake")
    with pytest.raises(ValueError, match="ingest needs a local lake root"):
        main(["ingest", "2024-01", "--sample", "--sample-rows", "10"])
