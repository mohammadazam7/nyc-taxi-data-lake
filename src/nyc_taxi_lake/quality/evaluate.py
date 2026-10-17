"""Evaluate a check suite against one month of the lake with Spark.

Each check becomes a single aggregate (or, for referential integrity, an anti-join), so a
suite of twenty checks costs about twenty small Spark jobs over cached month data. A
check that cannot be evaluated, because a table is missing or a column does not exist,
fails with the reason in ``detail`` instead of aborting the run: a broken input is a
quality breach in its own right and should reach the alert sink.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path

from pyspark.errors import AnalysisException
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from nyc_taxi_lake.config import Settings
from nyc_taxi_lake.ingest.raw_zone import partition_dir
from nyc_taxi_lake.months import Month
from nyc_taxi_lake.quality.report import CheckResult
from nyc_taxi_lake.quality.spec import (
    Check,
    Freshness,
    NullRate,
    QuarantineRate,
    ReferentialIntegrity,
    RowCountReconciles,
    ValueRange,
    kind_of,
)

ORPHAN_SAMPLE = 5


class MonthTables:
    """Lazily read and cache the tables a suite needs for one month."""

    def __init__(self, spark: SparkSession, settings: Settings, month: Month) -> None:
        self.spark = spark
        self.settings = settings
        self.month = month
        self._cache: dict[str, DataFrame] = {}

    def _path(self, name: str) -> Path:
        s, taxi = self.settings, self.settings.taxi_type
        if name == "raw":
            return partition_dir(s.raw_root, taxi, self.month)
        if name == "quarantine":
            return s.quarantine_root / taxi / self.month.partition
        if name == "clean":
            return s.clean_root / taxi
        return s.warehouse_root / taxi / name

    def _month_filter(self, frame: DataFrame) -> DataFrame:
        nxt = self.month.next()
        first, after = date(self.month.year, self.month.month, 1), date(nxt.year, nxt.month, 1)
        return frame.filter((F.col("pickup_date") >= first) & (F.col("pickup_date") < after))

    def get(self, name: str) -> DataFrame:
        if name not in self._cache:
            path = self._path(name)
            if not path.exists():
                raise FileNotFoundError(f"{name} not found at {path}")
            frame = self.spark.read.parquet(str(path))
            if name in ("clean", "fact_trips"):
                frame = self._month_filter(frame)
            self._cache[name] = frame.cache()
        return self._cache[name]

    def count(self, name: str) -> int:
        return int(self.get(name).count())

    def release(self) -> None:
        for frame in self._cache.values():
            frame.unpersist()
        self._cache.clear()


def _pct(value: float) -> str:
    return f"{value:.2%}"


def _row_count(check: RowCountReconciles, t: MonthTables) -> CheckResult:
    source, target = t.count(check.source), t.count(check.target)
    if check.source == "raw":
        quarantined = t.count("quarantine")
        unaccounted = source - target - quarantined
        detail = f"raw {source:,}, clean {target:,}, quarantined {quarantined:,}"
    else:
        unaccounted = source - target
        detail = f"{check.source} {source:,}, {check.target} {target:,}"
    return CheckResult(
        check.name, "row_count", check.severity, unaccounted == 0, unaccounted, "== 0", detail
    )


def _quarantine_rate(check: QuarantineRate, t: MonthTables) -> CheckResult:
    raw, quarantined = t.count("raw"), t.count("quarantine")
    threshold = f"<= {_pct(check.max)}"
    if raw == 0:
        return CheckResult(
            check.name, "quarantine_rate", check.severity, False, None, threshold, "no raw rows"
        )
    rate = quarantined / raw
    detail = f"{quarantined:,} of {raw:,} raw rows quarantined"
    return CheckResult(
        check.name, "quarantine_rate", check.severity, rate <= check.max, rate, threshold, detail
    )


def _null_rate(check: NullRate, t: MonthTables) -> CheckResult:
    row = (
        t.get(check.table)
        .agg(F.count(F.lit(1)).alias("rows"), F.count_if(F.col(check.column).isNull()).alias("n"))
        .first()
    )
    assert row is not None
    rows, nulls = int(row["rows"]), int(row["n"])
    rate = nulls / rows if rows else 0.0
    return CheckResult(
        check.name,
        "null_rate",
        check.severity,
        rate <= check.max,
        rate,
        f"<= {_pct(check.max)}",
        f"{nulls:,} of {rows:,} rows null",
    )


def _range(check: ValueRange, t: MonthTables) -> CheckResult:
    col = F.col(check.column)
    outside = F.lit(False)
    if check.min is not None:
        outside = outside | (col < check.min)
    if check.max is not None:
        outside = outside | (col > check.max)
    row = (
        t.get(check.table)
        .agg(F.count(col).alias("values"), F.count_if(outside).alias("bad"))
        .first()
    )
    assert row is not None
    values, bad = int(row["values"]), int(row["bad"])
    rate = bad / values if values else 0.0
    bounds = f"[{'-inf' if check.min is None else check.min}, "
    bounds += f"{'inf' if check.max is None else check.max}]"
    return CheckResult(
        check.name,
        "range",
        check.severity,
        rate <= check.max_violation_rate,
        rate,
        f"<= {_pct(check.max_violation_rate)} outside {bounds}",
        f"{bad:,} of {values:,} values outside",
    )


def _referential_integrity(check: ReferentialIntegrity, t: MonthTables) -> CheckResult:
    keys = t.get(check.dimension).select(F.col(check.key).alias("_key")).distinct()
    facts = t.get(check.table).select(F.col(check.column).alias("_key"))
    orphans = facts.join(keys, on="_key", how="left_anti").cache()
    try:
        count = orphans.count()
        sample = [r["_key"] for r in orphans.distinct().limit(ORPHAN_SAMPLE).collect()]
    finally:
        orphans.unpersist()
    detail = f"{count:,} rows without a match in {check.references}"
    if sample:
        detail += f"; e.g. {', '.join(map(str, sample))}"
    return CheckResult(
        check.name, "referential_integrity", check.severity, count == 0, count, "== 0", detail
    )


def _freshness(check: Freshness, t: MonthTables) -> CheckResult:
    nxt = t.month.next()
    month_end = datetime(nxt.year, nxt.month, 1)
    threshold = f"<= {check.max_gap_hours:g}h before month end"
    newest = t.get(check.table).agg(F.max(check.column).alias("newest")).first()
    assert newest is not None
    latest = newest["newest"]
    if latest is None:
        return CheckResult(
            check.name, "freshness", check.severity, False, None, threshold, "no rows"
        )
    if isinstance(latest, datetime) and latest.tzinfo is not None:
        latest = latest.replace(tzinfo=None)
    gap_h = (month_end - latest).total_seconds() / 3600
    return CheckResult(
        check.name,
        "freshness",
        check.severity,
        gap_h <= check.max_gap_hours,
        round(gap_h, 2),
        threshold,
        f"newest {check.column} is {latest.isoformat(sep=' ')}",
    )


def _dispatch(check: Check, t: MonthTables) -> CheckResult:
    match check:
        case RowCountReconciles():
            return _row_count(check, t)
        case QuarantineRate():
            return _quarantine_rate(check, t)
        case NullRate():
            return _null_rate(check, t)
        case ValueRange():
            return _range(check, t)
        case ReferentialIntegrity():
            return _referential_integrity(check, t)
        case Freshness():
            return _freshness(check, t)


def evaluate_check(check: Check, tables: MonthTables) -> CheckResult:
    try:
        return _dispatch(check, tables)
    except (FileNotFoundError, AnalysisException) as exc:
        reason = str(exc).splitlines()[0]
        return CheckResult(check.name, kind_of(check), check.severity, False, None, "-", reason)


def evaluate_suite(checks: Iterable[Check], tables: MonthTables) -> list[CheckResult]:
    return [evaluate_check(check, tables) for check in checks]
