"""Lake locations that are either local folders or S3 prefixes.

Spark reads and writes both through a URI string, so the jobs only need the few file
operations they do themselves: check that an input exists, and write small JSON run
summaries and reports. :class:`LakePath` is that subset; :class:`pathlib.Path` already
satisfies it and :class:`S3Path` implements it with boto3.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, Self

S3_SCHEMES = ("s3://", "s3a://")


class LakePath(Protocol):
    @property
    def name(self) -> str: ...

    def __truediv__(self, key: str) -> Self: ...

    def exists(self) -> bool: ...

    def mkdir(self, *, parents: bool = ..., exist_ok: bool = ...) -> None: ...

    def read_text(self) -> str: ...

    def write_text(self, data: str) -> int: ...


class S3Path:
    """An object key or key prefix in a bucket, e.g. ``s3://lake/clean/yellow``.

    ``str()`` gives the URI Spark expects. S3 has no directories: ``exists`` is true for
    an object with this key or for any object under ``key/``, and ``mkdir`` does nothing.
    """

    def __init__(self, uri: str, client: Any = None) -> None:
        scheme = next((s for s in S3_SCHEMES if uri.startswith(s)), None)
        if scheme is None:
            raise ValueError(f"not an S3 URI: {uri!r}")
        bucket, _, key = uri[len(scheme) :].partition("/")
        if not bucket:
            raise ValueError(f"S3 URI has no bucket: {uri!r}")
        self.scheme = scheme
        self.bucket = bucket
        self.key = key.strip("/")
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                import boto3
            except ImportError as exc:  # pragma: no cover - depends on the environment
                raise RuntimeError("an S3 lake root needs the [aws] extra") from exc
            self._client = boto3.client("s3")
        return self._client

    @property
    def name(self) -> str:
        return self.key.rsplit("/", 1)[-1]

    def __truediv__(self, key: str) -> S3Path:
        joined = f"{self.key}/{key.strip('/')}" if self.key else key.strip("/")
        return S3Path(f"{self.scheme}{self.bucket}/{joined}", self._client)

    def __str__(self) -> str:
        root = f"{self.scheme}{self.bucket}"
        return f"{root}/{self.key}" if self.key else root

    def __repr__(self) -> str:
        return f"S3Path({str(self)!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, S3Path) and str(self) == str(other)

    def __hash__(self) -> int:
        return hash(str(self))

    def exists(self) -> bool:
        # Listing "<key>/" rather than "<key>" keeps the request inside the "<prefix>/*"
        # patterns the Glue job roles are allowed to list.
        prefix = f"{self.key}/" if self.key else ""
        listing = self.client.list_objects_v2(Bucket=self.bucket, Prefix=prefix, MaxKeys=1)
        if listing.get("Contents"):
            return True
        if not self.key:
            return False
        try:
            self.client.head_object(Bucket=self.bucket, Key=self.key)
        except Exception as exc:
            error = getattr(exc, "response", {}).get("Error", {})
            if error.get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise
        return True

    def mkdir(self, *, parents: bool = False, exist_ok: bool = False) -> None:
        """Nothing to do: S3 creates prefixes implicitly."""

    def read_text(self) -> str:
        body = self.client.get_object(Bucket=self.bucket, Key=self.key)["Body"].read()
        return str(body.decode("utf-8"))

    def write_text(self, data: str) -> int:
        encoded = data.encode("utf-8")
        self.client.put_object(Bucket=self.bucket, Key=self.key, Body=encoded)
        return len(encoded)


def lake_path(location: str) -> Path | S3Path:
    """Parse a lake location: an ``s3://`` URI, or a local path made absolute."""
    if location.startswith(S3_SCHEMES):
        return S3Path(location)
    return Path(location).resolve()


def require_local(path: LakePath, purpose: str) -> Path:
    """Return ``path`` as a local :class:`Path`, or explain that ``purpose`` needs one."""
    if isinstance(path, Path):
        return path
    raise ValueError(f"{purpose} needs a local lake root, not {path}")
