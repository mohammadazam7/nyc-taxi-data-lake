"""Write conformed trip files into the raw zone with a manifest per partition.

Layout (mirrors the S3 layout used in AWS)::

    raw/yellow/year=2024/month=01/part-0000.parquet
    raw/yellow/year=2024/month=01/_manifest.json

The manifest records the source, row count and content hash. Re-running ingest for a
month whose source hash has not changed is a no-op, which makes backfills safe to retry.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

import pyarrow as pa
import pyarrow.parquet as pq

from nyc_taxi_lake.months import Month
from nyc_taxi_lake.paths import LakePath
from nyc_taxi_lake.schema import conform

log = logging.getLogger(__name__)

MANIFEST = "_manifest.json"


@dataclass(frozen=True)
class Manifest:
    month: str
    source: str
    source_sha256: str
    rows: int
    ingested_at: str


@dataclass(frozen=True)
class IngestResult:
    month: str
    path: Path
    rows: int
    skipped: bool


P = TypeVar("P", bound=LakePath)


def partition_dir(raw_root: P, taxi_type: str, month: Month) -> P:
    return raw_root / taxi_type / month.partition


def table_sha256(table: pa.Table) -> str:
    sink = pa.BufferOutputStream()
    pq.write_table(table, sink, compression="none")
    return hashlib.sha256(sink.getvalue().to_pybytes()).hexdigest()


def read_manifest(directory: Path) -> Manifest | None:
    path = directory / MANIFEST
    if not path.exists():
        return None
    return Manifest(**json.loads(path.read_text()))


def write_partition(
    table: pa.Table,
    raw_root: Path,
    taxi_type: str,
    month: Month,
    source: str,
    force: bool = False,
) -> IngestResult:
    """Conform ``table`` and land it as a single raw partition, idempotently."""
    conformed = conform(table)
    digest = table_sha256(conformed)
    directory = partition_dir(raw_root, taxi_type, month)

    existing = read_manifest(directory)
    if existing and existing.source_sha256 == digest and not force:
        log.info("%s unchanged since %s, skipping", month.key, existing.ingested_at)
        return IngestResult(month.key, directory, existing.rows, skipped=True)

    directory.mkdir(parents=True, exist_ok=True)
    for old in directory.glob("part-*.parquet"):
        old.unlink()
    pq.write_table(conformed, directory / "part-0000.parquet", compression="snappy")

    manifest = Manifest(
        month=month.key,
        source=source,
        source_sha256=digest,
        rows=conformed.num_rows,
        ingested_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    (directory / MANIFEST).write_text(json.dumps(asdict(manifest), indent=2))
    log.info("landed %s: %d rows -> %s", month.key, conformed.num_rows, directory)
    return IngestResult(month.key, directory, conformed.num_rows, skipped=False)
