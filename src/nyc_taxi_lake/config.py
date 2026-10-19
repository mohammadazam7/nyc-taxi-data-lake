"""Runtime settings, read from environment variables with safe local defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Where the lake lives and how to reach the TLC source.

    Every value can be overridden with an ``NYC_LAKE_*`` environment variable so the
    same code runs on a laptop (local folders) and in AWS (S3 prefixes).
    """

    lake_root: Path
    tlc_base_url: str
    taxi_type: str
    http_timeout_s: int
    http_retries: int

    @property
    def raw_root(self) -> Path:
        return self.lake_root / "raw"

    @property
    def clean_root(self) -> Path:
        return self.lake_root / "clean"

    @property
    def quarantine_root(self) -> Path:
        return self.lake_root / "quarantine"

    @property
    def warehouse_root(self) -> Path:
        return self.lake_root / "warehouse"

    @property
    def quality_root(self) -> Path:
        return self.lake_root / "quality"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            lake_root=Path(os.environ.get("NYC_LAKE_ROOT", "./lake")).resolve(),
            tlc_base_url=os.environ.get(
                "NYC_LAKE_TLC_BASE_URL", "https://d37ci6vzurychx.cloudfront.net/trip-data"
            ).rstrip("/"),
            taxi_type=os.environ.get("NYC_LAKE_TAXI_TYPE", "yellow"),
            http_timeout_s=int(os.environ.get("NYC_LAKE_HTTP_TIMEOUT", "120")),
            http_retries=int(os.environ.get("NYC_LAKE_HTTP_RETRIES", "3")),
        )
