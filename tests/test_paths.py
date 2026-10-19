from __future__ import annotations

import io
from pathlib import Path
from typing import Any, ClassVar

import pytest

from nyc_taxi_lake.paths import LakePath, S3Path, lake_path, require_local


class NotFoundError(Exception):
    """Shaped like botocore's ClientError for a missing key."""

    response: ClassVar[dict[str, Any]] = {"Error": {"Code": "404"}}


class FakeS3:
    """The S3 calls S3Path makes, over an in-memory bucket."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.prefixes_listed: list[str] = []

    def list_objects_v2(self, *, Bucket: str, Prefix: str, MaxKeys: int) -> dict[str, Any]:
        self.prefixes_listed.append(Prefix)
        keys = sorted(k for b, k in self.objects if b == Bucket and k.startswith(Prefix))
        return {"Contents": [{"Key": k} for k in keys[:MaxKeys]]} if keys else {}

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        if (Bucket, Key) not in self.objects:
            raise NotFoundError
        return {}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> None:
        self.objects[(Bucket, Key)] = Body


def test_parses_bucket_and_key() -> None:
    p = S3Path("s3://lake/clean/yellow/")
    assert (p.bucket, p.key) == ("lake", "clean/yellow")
    assert str(p) == "s3://lake/clean/yellow"


def test_join_keeps_the_scheme() -> None:
    root = S3Path("s3a://lake")
    assert str(root / "raw" / "yellow" / "year=2024/month=01") == (
        "s3a://lake/raw/yellow/year=2024/month=01"
    )
    assert (root / "raw" / "x.json").name == "x.json"


@pytest.mark.parametrize("uri", ["lake/raw", "s3://", "/tmp/lake"])
def test_rejects_non_s3_uris(uri: str) -> None:
    with pytest.raises(ValueError):
        S3Path(uri)


def test_write_then_read_text() -> None:
    s3 = FakeS3()
    path = S3Path("s3://lake", client=s3) / "clean" / "_runs" / "2024-01.json"
    path.mkdir(parents=True, exist_ok=True)
    assert path.write_text('{"rows": 3}') == 11
    assert s3.objects[("lake", "clean/_runs/2024-01.json")] == b'{"rows": 3}'
    assert path.read_text() == '{"rows": 3}'


def test_exists_for_objects_and_prefixes() -> None:
    s3 = FakeS3()
    s3.objects[("lake", "raw/yellow/year=2024/month=01/part-0.parquet")] = b""
    root = S3Path("s3://lake", client=s3)
    assert (root / "raw" / "yellow").exists()
    assert (root / "raw/yellow/year=2024/month=01/part-0.parquet").exists()
    # A shared string prefix is not a parent folder.
    assert not (root / "raw" / "yell").exists()
    assert not (root / "clean").exists()
    # Every listing stays under a "<prefix>/" so it matches the job roles' policies.
    assert all(p.endswith("/") for p in s3.prefixes_listed)


def test_exists_raises_other_errors() -> None:
    class Denied(Exception):
        response: ClassVar[dict[str, Any]] = {"Error": {"Code": "403"}}

    class DenyingS3(FakeS3):
        def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
            raise Denied

    with pytest.raises(Denied):
        (S3Path("s3://lake", client=DenyingS3()) / "raw" / "x.csv").exists()


def test_lake_path_picks_the_implementation(tmp_path: Path) -> None:
    assert isinstance(lake_path("s3://lake"), S3Path)
    local = lake_path(str(tmp_path / "lake"))
    assert isinstance(local, Path) and local.is_absolute()


def test_require_local() -> None:
    local: LakePath = Path("lake")
    assert require_local(local, "ingest") == Path("lake")
    with pytest.raises(ValueError, match="ingest needs a local lake root"):
        require_local(S3Path("s3://lake"), "ingest")
