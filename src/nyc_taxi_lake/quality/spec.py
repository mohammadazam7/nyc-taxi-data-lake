"""Declarative data-quality checks, loaded from TOML.

A suite is a list of ``[[check]]`` tables. Every check has a ``kind`` and a
``severity``; the remaining keys depend on the kind::

    [[check]]
    kind = "null_rate"
    table = "fact_trips"
    column = "pickup_zone_key"
    max = 0.0
    severity = "error"

Parsing is strict: an unknown kind, a missing key or an unexpected key is an error that
names the check, so a typo in the suite fails loudly instead of silently skipping a check.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Literal

Severity = Literal["error", "warn"]
SEVERITIES: tuple[Severity, ...] = ("error", "warn")

# The tables a check can point at. "raw" and "clean" are the month's partitions in
# those zones; the warehouse tables are read from the warehouse zone.
TABLES = (
    "raw",
    "clean",
    "fact_trips",
    "dim_date",
    "dim_zone",
    "dim_vendor",
    "dim_rate_code",
    "dim_payment_type",
)


class SpecError(ValueError):
    """The check suite is malformed."""


@dataclass(frozen=True)
class RowCountReconciles:
    """Every row is accounted for between two stages.

    ``raw -> clean`` holds when raw rows equal clean plus quarantined rows;
    ``clean -> fact_trips`` holds when the counts are equal.
    """

    name: str
    severity: Severity
    source: str
    target: str


@dataclass(frozen=True)
class QuarantineRate:
    """Share of the month's raw rows sent to quarantine is at most ``max``."""

    name: str
    severity: Severity
    max: float


@dataclass(frozen=True)
class NullRate:
    """Share of nulls in ``table.column`` is at most ``max``."""

    name: str
    severity: Severity
    table: str
    column: str
    max: float


@dataclass(frozen=True)
class ValueRange:
    """Share of non-null values outside ``[min, max]`` is at most ``max_violation_rate``."""

    name: str
    severity: Severity
    table: str
    column: str
    min: float | None
    max: float | None
    max_violation_rate: float


@dataclass(frozen=True)
class ReferentialIntegrity:
    """Every ``table.column`` value exists in ``references`` (``dim_table.key_column``)."""

    name: str
    severity: Severity
    table: str
    column: str
    references: str

    @property
    def dimension(self) -> str:
        return self.references.split(".", 1)[0]

    @property
    def key(self) -> str:
        return self.references.split(".", 1)[1]


@dataclass(frozen=True)
class Freshness:
    """The month's newest trip starts within ``max_gap_hours`` of the month's end.

    TLC publishes whole months, so a file whose last trip is days before the end of the
    month has almost certainly been truncated somewhere between TLC and the lake.
    """

    name: str
    severity: Severity
    table: str
    column: str
    max_gap_hours: float


Check = (
    RowCountReconciles | QuarantineRate | NullRate | ValueRange | ReferentialIntegrity | Freshness
)

# kind -> (class, required keys, optional keys with defaults)
_KINDS: dict[str, tuple[type[Check], set[str], dict[str, Any]]] = {
    "row_count": (RowCountReconciles, {"source", "target"}, {}),
    "quarantine_rate": (QuarantineRate, {"max"}, {}),
    "null_rate": (NullRate, {"table", "column", "max"}, {}),
    "range": (
        ValueRange,
        {"table", "column"},
        {"min": None, "max": None, "max_violation_rate": 0.0},
    ),
    "referential_integrity": (ReferentialIntegrity, {"table", "column", "references"}, {}),
    "freshness": (Freshness, {"table", "column", "max_gap_hours"}, {}),
}

_RECONCILE_PAIRS = {("raw", "clean"), ("clean", "fact_trips")}


def _default_name(kind: str, entry: dict[str, Any]) -> str:
    if kind == "row_count":
        return f"row_count:{entry['source']}->{entry['target']}"
    if kind == "quarantine_rate":
        return "quarantine_rate"
    return f"{kind}:{entry['table']}.{entry['column']}"


def _rate(value: Any, where: str, key: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not 0 <= value <= 1:
        raise SpecError(f"{where}: {key} must be a number between 0 and 1, got {value!r}")
    return float(value)


def _validate(check: Check, where: str) -> None:
    if isinstance(check, RowCountReconciles):
        if (check.source, check.target) not in _RECONCILE_PAIRS:
            pairs = ", ".join(f"{s}->{t}" for s, t in sorted(_RECONCILE_PAIRS))
            raise SpecError(f"{where}: row_count supports {pairs}")
        return
    if isinstance(check, QuarantineRate):
        _rate(check.max, where, "max")
        return
    if check.table not in TABLES:
        raise SpecError(f"{where}: unknown table {check.table!r}")
    if isinstance(check, NullRate):
        _rate(check.max, where, "max")
    elif isinstance(check, ValueRange):
        if check.min is None and check.max is None:
            raise SpecError(f"{where}: range needs min, max or both")
        if check.min is not None and check.max is not None and check.min > check.max:
            raise SpecError(f"{where}: min is greater than max")
        _rate(check.max_violation_rate, where, "max_violation_rate")
    elif isinstance(check, ReferentialIntegrity):
        if check.references.count(".") != 1 or check.dimension not in TABLES:
            raise SpecError(f"{where}: references must be '<dim_table>.<column>'")
    elif isinstance(check, Freshness) and check.max_gap_hours < 0:
        raise SpecError(f"{where}: max_gap_hours must not be negative")


def parse_check(entry: dict[str, Any], index: int) -> Check:
    where = f"check #{index + 1}"
    kind = entry.get("kind")
    if kind not in _KINDS:
        raise SpecError(f"{where}: unknown kind {kind!r}; expected one of {sorted(_KINDS)}")
    cls, required, optional = _KINDS[kind]
    where = f"{where} ({kind})"

    missing = required - entry.keys()
    if missing:
        raise SpecError(f"{where}: missing {', '.join(sorted(missing))}")
    allowed = required | optional.keys() | {"kind", "name", "severity"}
    extra = entry.keys() - allowed
    if extra:
        raise SpecError(f"{where}: unexpected {', '.join(sorted(extra))}")

    severity = entry.get("severity", "error")
    if severity not in SEVERITIES:
        raise SpecError(f"{where}: severity must be 'error' or 'warn', got {severity!r}")

    fields = {**optional, **{k: entry[k] for k in required | optional.keys() if k in entry}}
    check = cls(name=entry.get("name") or _default_name(kind, entry), severity=severity, **fields)
    _validate(check, where)
    return check


def parse_suite(document: dict[str, Any]) -> list[Check]:
    entries = document.get("check", [])
    if not isinstance(entries, list) or not entries:
        raise SpecError("a suite needs at least one [[check]] table")
    checks = [parse_check(entry, i) for i, entry in enumerate(entries)]
    names = [c.name for c in checks]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise SpecError(f"check names must be unique; repeated: {', '.join(duplicates)}")
    return checks


def load_suite(path: Path | None = None) -> list[Check]:
    """Load a suite from ``path``, or the default suite shipped with the package."""
    if path is None:
        text = resources.files("nyc_taxi_lake.quality").joinpath("checks.toml").read_text()
    else:
        text = path.read_text()
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise SpecError(f"{path or 'default suite'}: {exc}") from exc
    return parse_suite(document)
