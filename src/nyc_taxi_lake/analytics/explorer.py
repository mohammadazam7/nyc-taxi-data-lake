"""Render an :class:`AnalyticsReport` as an interactive, self-contained explorer page.

The static dashboard (:mod:`nyc_taxi_lake.analytics.dashboard`) stays the CI artifact:
no scripts, readable anywhere. The explorer is for working with a report: a rotatable
3D view of demand by weekday and hour, a daily timeline whose selection drives the
summary figures, sortable zones and a payment breakdown.

The page is still one file with no external requests. The report is embedded as JSON
and drawn on canvas by inline script, so it opens from disk or a static S3 object in
the same way the dashboard does.
"""

from __future__ import annotations

import json
from html import escape
from importlib.resources import files
from typing import Any

from nyc_taxi_lake.analytics.results import AnalyticsReport

REQUIRED = (
    "monthly_revenue",
    "daily_trips",
    "hourly_demand",
    "busiest_pickup_zones",
    "payment_mix",
)


def _template() -> str:
    return files("nyc_taxi_lake.analytics").joinpath("explorer.html").read_text(encoding="utf-8")


def payload(report: AnalyticsReport, *, source_note: str = "") -> dict[str, Any]:
    """The data the page needs: the report itself plus the provenance note."""
    missing = [name for name in REQUIRED if name not in {r.name for r in report.results}]
    if missing:
        raise ValueError(f"report is missing results: {', '.join(missing)}")
    data = report.to_dict()
    data["source_note"] = source_note
    return data


def embed_json(data: dict[str, Any]) -> str:
    """JSON that is safe inside a ``<script>`` element.

    ``</`` would end the element early, so it is written as ``<\\/``. Non-ASCII text is
    escaped as well, which keeps the page ASCII whatever encoding it is written with.
    The result still parses as the same JSON.
    """
    text = json.dumps(data, separators=(",", ":"), allow_nan=False)
    return text.replace("</", "<\\/")


def render(report: AnalyticsReport, *, source_note: str = "") -> str:
    """The explorer for ``report`` as a complete HTML document."""
    taxi = report.taxi_type.capitalize()
    span = report.start if report.start == report.end else f"{report.start} to {report.end}"
    return (
        _template()
        .replace("__TITLE__", escape(f"NYC {taxi} taxi explorer, {span}"))
        .replace("__DATA__", embed_json(payload(report, source_note=source_note)))
    )
