from __future__ import annotations

from pathlib import Path

import pyarrow.compute as pc
import pyarrow.parquet as pq
import pytest
import requests

from nyc_taxi_lake.config import Settings
from nyc_taxi_lake.ingest.raw_zone import read_manifest, write_partition
from nyc_taxi_lake.ingest.sample import generate_month
from nyc_taxi_lake.ingest.tlc import DownloadError, download_month, trip_file_url
from nyc_taxi_lake.months import Month
from nyc_taxi_lake.schema import YELLOW_TRIP_SCHEMA

JAN = Month(2024, 1)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        lake_root=tmp_path,
        tlc_base_url="https://example.test/trip-data",
        taxi_type="yellow",
        http_timeout_s=5,
        http_retries=2,
    )


def test_sample_matches_schema_and_contains_defects() -> None:
    table = generate_month(JAN, rows=2_000)
    assert table.schema == YELLOW_TRIP_SCHEMA
    assert table.num_rows > 2_000  # duplicates were appended
    assert pc.sum(pc.less(table.column("fare_amount"), 0)).as_py() > 0


def test_sample_is_deterministic() -> None:
    assert generate_month(JAN, rows=500).equals(generate_month(JAN, rows=500))


def test_write_partition_is_idempotent(settings: Settings) -> None:
    table = generate_month(JAN, rows=1_000)
    first = write_partition(table, settings.raw_root, "yellow", JAN, "synthetic://test")
    second = write_partition(table, settings.raw_root, "yellow", JAN, "synthetic://test")

    assert not first.skipped and second.skipped
    assert first.path == settings.raw_root / "yellow" / "year=2024" / "month=01"
    manifest = read_manifest(first.path)
    assert manifest is not None and manifest.rows == table.num_rows
    assert pq.read_table(first.path / "part-0000.parquet").num_rows == table.num_rows


def test_write_partition_rewrites_when_source_changes(settings: Settings) -> None:
    write_partition(generate_month(JAN, 500, seed=1), settings.raw_root, "yellow", JAN, "a")
    result = write_partition(
        generate_month(JAN, 800, seed=1), settings.raw_root, "yellow", JAN, "b"
    )
    assert not result.skipped
    assert len(list(result.path.glob("part-*.parquet"))) == 1


class _FakeResponse:
    def __init__(self, status: int, body: bytes = b"") -> None:
        self.status_code = status
        self._body = body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def iter_content(self, chunk_size: int) -> list[bytes]:
        return [self._body]


class _FakeSession:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self.responses = responses
        self.calls = 0

    def get(self, url: str, **_: object) -> _FakeResponse:
        self.calls += 1
        return self.responses.pop(0)


def test_download_retries_then_succeeds(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("nyc_taxi_lake.ingest.tlc.time.sleep", lambda _: None)
    session = _FakeSession([_FakeResponse(503), _FakeResponse(200, b"PAR1")])
    path = download_month(settings, JAN, tmp_path / "dl", session=session)  # type: ignore[arg-type]
    assert session.calls == 2
    assert path.read_bytes() == b"PAR1"
    assert not list((tmp_path / "dl").glob("*.part"))


def test_download_404_fails_fast(settings: Settings, tmp_path: Path) -> None:
    session = _FakeSession([_FakeResponse(404)])
    with pytest.raises(DownloadError, match="not published"):
        download_month(settings, JAN, tmp_path, session=session)  # type: ignore[arg-type]
    assert session.calls == 1


def test_url_format(settings: Settings) -> None:
    assert (
        trip_file_url(settings, JAN)
        == "https://example.test/trip-data/yellow_tripdata_2024-01.parquet"
    )
