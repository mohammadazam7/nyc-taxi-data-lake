"""Helpers for the ``YYYY-MM`` month keys that partition the lake."""

from __future__ import annotations

import re
from dataclasses import dataclass

_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")


@dataclass(frozen=True, order=True)
class Month:
    year: int
    month: int

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12:
            raise ValueError(f"month must be 1-12, got {self.month}")
        if self.year < 2009:
            raise ValueError("TLC trip records start in 2009")

    @classmethod
    def parse(cls, value: str) -> Month:
        match = _MONTH_RE.match(value.strip())
        if not match:
            raise ValueError(f"expected YYYY-MM, got {value!r}")
        return cls(int(match.group(1)), int(match.group(2)))

    @property
    def key(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    @property
    def partition(self) -> str:
        """Hive-style partition path understood by Glue, Athena and Spark."""
        return f"year={self.year:04d}/month={self.month:02d}"

    def next(self) -> Month:
        if self.month == 12:
            return Month(self.year + 1, 1)
        return Month(self.year, self.month + 1)


def month_range(start: str, end: str) -> list[Month]:
    """Inclusive list of months between two ``YYYY-MM`` keys."""
    first, last = Month.parse(start), Month.parse(end)
    if first > last:
        raise ValueError(f"start {start} is after end {end}")
    out = [first]
    while out[-1] < last:
        out.append(out[-1].next())
    return out
