"""Query results in a form that serialises to JSON and renders without a database."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

Scalar = str | int | float | bool | None


def to_scalar(value: object) -> Scalar:
    """Map a driver value onto a JSON scalar.

    Money arrives as :class:`~decimal.Decimal` and becomes the nearest float, which is
    exact enough for display; the warehouse keeps the decimal values.
    """
    if value is None or isinstance(value, str | bool | int | float):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    raise TypeError(f"cannot store {type(value).__name__} in a query result")


@dataclass(frozen=True)
class QueryResult:
    name: str
    columns: tuple[str, ...]
    rows: tuple[tuple[Scalar, ...], ...]

    @classmethod
    def from_records(
        cls, name: str, columns: Sequence[str], records: Sequence[Sequence[object]]
    ) -> QueryResult:
        width = len(columns)
        rows = []
        for record in records:
            if len(record) != width:
                raise ValueError(f"{name}: row has {len(record)} values, expected {width}")
            rows.append(tuple(to_scalar(v) for v in record))
        return cls(name=name, columns=tuple(columns), rows=tuple(rows))

    def column(self, column: str) -> list[Scalar]:
        index = self.columns.index(column)
        return [row[index] for row in self.rows]

    def records(self) -> list[dict[str, Scalar]]:
        return [dict(zip(self.columns, row, strict=True)) for row in self.rows]

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "columns": list(self.columns), "rows": self.records()}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> QueryResult:
        columns = tuple(data["columns"])
        return cls.from_records(
            data["name"], columns, [tuple(row[c] for c in columns) for row in data["rows"]]
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
