"""Render an :class:`AnalyticsReport` as one self-contained HTML page.

The page has no scripts and no external requests: styles are inline and the charts are
SVG from :mod:`nyc_taxi_lake.analytics.svg`. It can therefore be opened from disk, served
as a static object from S3, or uploaded as a CI artifact, and it reads the same anywhere.
"""

from __future__ import annotations

from collections.abc import Sequence
from html import escape

from nyc_taxi_lake.analytics.results import AnalyticsReport, QueryResult
from nyc_taxi_lake.analytics.svg import heatmap, horizontal_bars, line_chart, stacked_bars

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

STYLE = """
:root {
  --bg: #ffffff; --fg: #1f2328; --muted: #59636e; --line: #d1d9e0;
  --c0: #2f6fb5; --c1: #e08a2e; --c2: #8a9aa9;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0d1117; --fg: #e6edf3; --muted: #9198a1; --line: #30363d;
    --c0: #5b9be0; --c1: #f0a050; --c2: #6e7b88;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font: 14px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
}
main { max-width: 800px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 22px; margin: 0 0 4px; }
h2 { font-size: 16px; margin: 32px 0 4px; }
p.note { color: var(--muted); margin: 0 0 12px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px; margin-top: 20px; }
.tile { border: 1px solid var(--line); border-radius: 6px; padding: 12px; }
.tile .k { color: var(--muted); font-size: 12px; }
.tile .v { font-size: 22px; font-variant-numeric: tabular-nums; }
.legend { color: var(--muted); font-size: 12px; margin-bottom: 4px; }
.legend span::before { content: ""; display: inline-block; width: 10px; height: 10px;
  margin: 0 4px 0 12px; vertical-align: -1px; background: var(--sw); }
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
th, td { text-align: right; padding: 4px 8px; border-bottom: 1px solid var(--line); }
th:first-child, td:first-child { text-align: left; }
th { color: var(--muted); font-weight: 600; }
svg { display: block; overflow: visible; }
svg .grid { stroke: var(--line); stroke-width: 1; }
svg .tick { fill: var(--muted); font-size: 11px; }
svg .series { fill: none; stroke: var(--c0); stroke-width: 2; }
svg .hit { fill: transparent; }
svg .s0 { fill: var(--c0); } svg .s1 { fill: var(--c1); } svg .s2 { fill: var(--c2); }
footer { color: var(--muted); font-size: 12px; margin-top: 40px; }
"""


def _floats(result: QueryResult, column: str) -> list[float]:
    return [float(v or 0) for v in result.column(column)]


def _tile(name: str, value: str) -> str:
    return (
        f'<div class="tile"><div class="k">{escape(name)}</div><div class="v">{value}</div></div>'
    )


def _legend(names: Sequence[str]) -> str:
    spans = "".join(
        f'<span style="--sw: var(--c{i})">{escape(n)}</span>' for i, n in enumerate(names)
    )
    return f'<div class="legend">{spans}</div>'


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{escape(c)}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _summary(report: AnalyticsReport) -> str:
    monthly = report.result("monthly_revenue")
    trips = sum(_floats(monthly, "trips"))
    revenue = sum(_floats(monthly, "revenue"))
    tips = sum(_floats(monthly, "tips"))
    fares = sum(_floats(monthly, "fares"))
    days = len(report.result("daily_trips").rows)
    return (
        '<div class="tiles">'
        + "".join(
            [
                _tile("Trips", f"{trips:,.0f}"),
                _tile("Revenue", f"${revenue:,.0f}"),
                _tile("Revenue per trip", f"${revenue / trips:,.2f}" if trips else "n/a"),
                _tile("Trips per day", f"{trips / days:,.0f}" if days else "n/a"),
                _tile("Tips as share of fares", f"{tips / fares:.1%}" if fares else "n/a"),
            ]
        )
        + "</div>"
    )


def _monthly(result: QueryResult) -> str:
    labels = [
        f"{MONTHS[int(m or 1) - 1]} {y}"
        for y, m in zip(result.column("year"), result.column("month"), strict=True)
    ]
    names = ("Fares", "Tips", "Other charges")
    series = [
        (name, _floats(result, column))
        for name, column in zip(names, ("fares", "tips", "other_charges"), strict=True)
    ]
    return _legend(names) + stacked_bars(labels, series, label="Revenue per month")


def _daily(result: QueryResult) -> str:
    days = [str(d)[5:] for d in result.column("calendar_date")]
    return line_chart(days, _floats(result, "trips"), label="Trips per day")


def _hourly(result: QueryResult) -> str:
    grid = [[0.0] * 24 for _ in WEEKDAYS]
    for row in result.records():
        grid[int(row["day_of_week"] or 1) - 1][int(row["pickup_hour"] or 0)] = float(
            row["trips"] or 0
        )
    hours = [f"{h:02d}" for h in range(24)]
    return heatmap(WEEKDAYS, hours, grid, label="Pickups by weekday and hour")


def _zones(result: QueryResult) -> str:
    labels = [f"{row['zone_name']} ({row['borough']})" for row in result.records()]
    return horizontal_bars(labels, _floats(result, "trips"), label="Busiest pickup zones")


def _payments(result: QueryResult) -> str:
    total = sum(_floats(result, "trips")) or 1
    rows = [
        (
            str(row["payment_type_name"]),
            f"{float(row['trips'] or 0):,.0f}",
            f"{float(row['trips'] or 0) / total:.1%}",
            f"${float(row['revenue'] or 0):,.0f}",
            "n/a" if row["tip_rate"] is None else f"{float(row['tip_rate']):.1%}",
        )
        for row in result.records()
    ]
    return _table(("Payment type", "Trips", "Share", "Revenue", "Tips / fares"), rows)


def render(report: AnalyticsReport, *, source_note: str = "") -> str:
    """The dashboard for ``report`` as a complete HTML document."""
    taxi = escape(report.taxi_type.capitalize())
    span = escape(report.start if report.start == report.end else f"{report.start} to {report.end}")
    sections = [
        (
            "Revenue per month",
            "Fares, tips, and surcharges, taxes and tolls.",
            _monthly,
            "monthly_revenue",
        ),
        ("Trips per day", "Pickups per calendar day, New York local time.", _daily, "daily_trips"),
        ("Demand by weekday and hour", "Darker cells have more pickups.", _hourly, "hourly_demand"),
        ("Busiest pickup zones", "Top 15 zones by pickups.", _zones, "busiest_pickup_zones"),
        (
            "Payment mix",
            "TLC records card tips only, so cash tip rates are near zero.",
            _payments,
            "payment_mix",
        ),
    ]
    body = [
        f"<h1>NYC {taxi} taxi trips, {span}</h1>",
        f'<p class="note">{escape(source_note)}</p>' if source_note else "",
        _summary(report),
    ]
    for title, note, draw, name in sections:
        body.append(f'<h2>{escape(title)}</h2><p class="note">{escape(note)}</p>')
        body.append(draw(report.result(name)))
    body.append(
        "<footer>Generated by nyc-lake dashboard from the analytics report; "
        "the SQL for every chart is in src/nyc_taxi_lake/analytics/sql.</footer>"
    )
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>NYC {taxi} taxi trips</title><style>{STYLE}</style></head>"
        f"<body><main>{''.join(body)}</main></body></html>\n"
    )
