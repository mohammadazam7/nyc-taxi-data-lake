"""Run the quality suite for a month, write the report and alert on breaches.

Layout::

    quality/yellow/2024-01.json     # one report per month, rewritten on each run

The report is written whatever the outcome, so the lake always holds the latest verdict
for every month. The alert sink is only called when at least one check is breached.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime

from pyspark.sql import SparkSession

from nyc_taxi_lake.config import Settings
from nyc_taxi_lake.months import Month
from nyc_taxi_lake.quality.alerts import AlertSink
from nyc_taxi_lake.quality.evaluate import MonthTables, evaluate_suite
from nyc_taxi_lake.quality.report import QualityReport
from nyc_taxi_lake.quality.spec import Check

log = logging.getLogger(__name__)


def check_month(
    spark: SparkSession,
    settings: Settings,
    month: Month,
    checks: Sequence[Check],
    sink: AlertSink,
) -> QualityReport:
    tables = MonthTables(spark, settings, month)
    try:
        results = evaluate_suite(checks, tables)
    finally:
        tables.release()

    report = QualityReport(
        month=month.key,
        taxi_type=settings.taxi_type,
        run_at=datetime.now(UTC).isoformat(timespec="seconds"),
        results=results,
    )
    path = report.write(settings.quality_root / settings.taxi_type)
    log.info("quality %s: %s (%s)", month.key, report.status.value, path)
    if report.breaches:
        sink.send(report)
    return report
