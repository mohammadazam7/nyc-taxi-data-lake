"""Download monthly trip files from the NYC TLC public endpoint."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import requests

from nyc_taxi_lake.config import Settings
from nyc_taxi_lake.months import Month

log = logging.getLogger(__name__)


class DownloadError(RuntimeError):
    """The TLC endpoint did not return a usable file."""


def trip_file_name(taxi_type: str, month: Month) -> str:
    return f"{taxi_type}_tripdata_{month.key}.parquet"


def trip_file_url(settings: Settings, month: Month) -> str:
    return f"{settings.tlc_base_url}/{trip_file_name(settings.taxi_type, month)}"


def download_month(
    settings: Settings,
    month: Month,
    dest_dir: Path,
    session: requests.Session | None = None,
) -> Path:
    """Stream one month's parquet file to ``dest_dir`` with retries and backoff.

    Writes to a ``.part`` file first and renames on success, so an interrupted
    download never leaves a truncated file that looks complete.
    """
    url = trip_file_url(settings, month)
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / trip_file_name(settings.taxi_type, month)
    partial = target.with_suffix(".parquet.part")
    http = session or requests.Session()

    last_error: Exception | None = None
    for attempt in range(1, settings.http_retries + 1):
        try:
            with http.get(url, stream=True, timeout=settings.http_timeout_s) as resp:
                if resp.status_code == 404:
                    raise DownloadError(f"{url} not published yet (404)")
                resp.raise_for_status()
                with partial.open("wb") as fh:
                    for chunk in resp.iter_content(chunk_size=1 << 20):
                        fh.write(chunk)
            partial.replace(target)
            log.info("downloaded %s (%d bytes)", url, target.stat().st_size)
            return target
        except DownloadError:
            raise
        except requests.RequestException as exc:
            last_error = exc
            wait = 2**attempt
            log.warning(
                "attempt %d/%d for %s failed: %s; retrying in %ds",
                attempt,
                settings.http_retries,
                url,
                exc,
                wait,
            )
            time.sleep(wait)
    partial.unlink(missing_ok=True)
    raise DownloadError(
        f"giving up on {url} after {settings.http_retries} attempts"
    ) from last_error
