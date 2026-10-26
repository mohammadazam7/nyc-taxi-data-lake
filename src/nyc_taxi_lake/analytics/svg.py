"""Minimal SVG chart primitives for the static dashboard.

The dashboard is a single HTML file that has to open from a laptop, an S3 bucket or a CI
artifact without a network connection, so the charts are drawn here as inline SVG rather
than with a JavaScript charting library. Each function returns an ``<svg>`` element as a
string; colours come from CSS custom properties defined by the page, so one palette serves
light and dark mode.

Every label is escaped, because zone names and payment types come from the data.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from html import escape

# Plot margins in SVG user units: room for the y-axis labels on the left and the x-axis
# labels below.
LEFT, RIGHT, TOP, BOTTOM = 56, 12, 12, 28


def nice_ceiling(value: float) -> float:
    """The smallest 1, 2, 2.5 or 5 times a power of ten that is at least ``value``.

    Axis maxima rounded this way give tick labels such as 0, 250, 500, 750, 1,000 instead
    of the data maximum split into awkward fractions.
    """
    if value <= 0:
        return 1.0
    magnitude = 10 ** math.floor(math.log10(value))
    for step in (1, 2, 2.5, 5, 10):
        if value <= step * magnitude:
            return float(step * magnitude)
    raise AssertionError("unreachable: step 10 always covers value")


def compact(value: float) -> str:
    """A short axis label: 950, 1.2k, 3.4M."""
    for divisor, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(value) >= divisor:
            return f"{value / divisor:.3g}{suffix}"
    return f"{value:.3g}"


def _open(width: int, height: int, label: str) -> str:
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" '
        f'aria-label="{escape(label)}" xmlns="http://www.w3.org/2000/svg">'
    )


def _y_axis(width: int, height: int, top_value: float, ticks: int = 4) -> list[str]:
    parts = []
    plot_h = height - TOP - BOTTOM
    for i in range(ticks + 1):
        value = top_value * i / ticks
        y = TOP + plot_h - plot_h * i / ticks
        parts.append(
            f'<line class="grid" x1="{LEFT}" x2="{width - RIGHT}" y1="{y:.1f}" y2="{y:.1f}"/>'
            f'<text class="tick" x="{LEFT - 6}" y="{y + 4:.1f}" text-anchor="end">'
            f"{compact(value)}</text>"
        )
    return parts


def line_chart(
    labels: Sequence[str],
    values: Sequence[float],
    *,
    label: str,
    width: int = 720,
    height: int = 220,
    label_every: int = 7,
) -> str:
    """One series as a line over evenly spaced categories, such as days."""
    if len(labels) != len(values):
        raise ValueError(f"{len(labels)} labels for {len(values)} values")
    top = nice_ceiling(max(values, default=0))
    plot_w = width - LEFT - RIGHT
    plot_h = height - TOP - BOTTOM
    step = plot_w / max(len(values) - 1, 1)

    parts = [_open(width, height, label), *_y_axis(width, height, top)]
    points = " ".join(
        f"{LEFT + i * step:.1f},{TOP + plot_h - plot_h * v / top:.1f}" for i, v in enumerate(values)
    )
    if points:
        parts.append(f'<polyline class="series" points="{points}"/>')
    for i in range(0, len(labels), label_every):
        parts.append(
            f'<text class="tick" x="{LEFT + i * step:.1f}" y="{height - 8}" '
            f'text-anchor="middle">{escape(labels[i])}</text>'
        )
    for i, (name, v) in enumerate(zip(labels, values, strict=True)):
        x = LEFT + i * step
        y = TOP + plot_h - plot_h * v / top
        parts.append(
            f'<circle class="hit" cx="{x:.1f}" cy="{y:.1f}" r="4">'
            f"<title>{escape(name)}: {v:,.0f}</title></circle>"
        )
    parts.append("</svg>")
    return "".join(parts)


def stacked_bars(
    labels: Sequence[str],
    series: Sequence[tuple[str, Sequence[float]]],
    *,
    label: str,
    width: int = 720,
    height: int = 220,
) -> str:
    """Vertical bars, one per label, each split into the named series from bottom up.

    Series are styled ``s0``, ``s1``, ... in order, which the page maps onto its palette.
    """
    for name, values in series:
        if len(values) != len(labels):
            raise ValueError(f"series {name!r} has {len(values)} values for {len(labels)} bars")
    totals = [sum(values[i] for _, values in series) for i in range(len(labels))]
    top = nice_ceiling(max(totals, default=0))
    plot_w = width - LEFT - RIGHT
    plot_h = height - TOP - BOTTOM
    slot = plot_w / max(len(labels), 1)
    bar_w = min(slot * 0.6, 96)

    parts = [_open(width, height, label), *_y_axis(width, height, top)]
    for i, bar_label in enumerate(labels):
        x = LEFT + slot * i + (slot - bar_w) / 2
        base = float(TOP + plot_h)
        for k, (name, values) in enumerate(series):
            h = plot_h * values[i] / top
            base -= h
            parts.append(
                f'<rect class="s{k}" x="{x:.1f}" y="{base:.1f}" width="{bar_w:.1f}" '
                f'height="{h:.1f}"><title>{escape(bar_label)} {escape(name)}: '
                f"{values[i]:,.0f}</title></rect>"
            )
        parts.append(
            f'<text class="tick" x="{x + bar_w / 2:.1f}" y="{height - 8}" '
            f'text-anchor="middle">{escape(bar_label)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def horizontal_bars(
    labels: Sequence[str],
    values: Sequence[float],
    *,
    label: str,
    width: int = 720,
    row_height: int = 22,
    label_width: int = 240,
) -> str:
    """Ranked horizontal bars with the category name on the left and the value on the right."""
    if len(labels) != len(values):
        raise ValueError(f"{len(labels)} labels for {len(values)} values")
    top = max(values, default=0) or 1
    value_width = 64
    plot_w = width - label_width - value_width
    height = row_height * len(labels) + 4

    parts = [_open(width, height, label)]
    for i, (name, v) in enumerate(zip(labels, values, strict=True)):
        y = 2 + i * row_height
        w = plot_w * v / top
        mid = y + row_height / 2 + 4
        parts.append(
            f'<text class="tick" x="{label_width - 8}" y="{mid:.1f}" text-anchor="end">'
            f"{escape(name)}</text>"
            f'<rect class="s0" x="{label_width}" y="{y + 3}" width="{w:.1f}" '
            f'height="{row_height - 6}"/>'
            f'<text class="tick" x="{label_width + w + 6:.1f}" y="{mid:.1f}">{v:,.0f}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def heatmap(
    row_labels: Sequence[str],
    column_labels: Sequence[str],
    cells: Sequence[Sequence[float]],
    *,
    label: str,
    width: int = 720,
    label_width: int = 40,
) -> str:
    """A grid whose cell opacity is proportional to its value, darkest at the maximum."""
    if len(cells) != len(row_labels) or any(len(r) != len(column_labels) for r in cells):
        raise ValueError("cells must have one row per row label and one column per column label")
    top = max((v for row in cells for v in row), default=0) or 1
    cell_w = (width - label_width) / max(len(column_labels), 1)
    cell_h = min(cell_w, 24)
    height = int(cell_h * len(row_labels) + 18)

    parts = [_open(width, height, label)]
    for r, (row_label, row) in enumerate(zip(row_labels, cells, strict=True)):
        y = r * cell_h
        parts.append(
            f'<text class="tick" x="{label_width - 6}" y="{y + cell_h / 2 + 4:.1f}" '
            f'text-anchor="end">{escape(row_label)}</text>'
        )
        for c, v in enumerate(row):
            parts.append(
                f'<rect class="s0" x="{label_width + c * cell_w:.1f}" y="{y:.1f}" '
                f'width="{cell_w - 1:.1f}" height="{cell_h - 1:.1f}" '
                f'fill-opacity="{0.06 + 0.94 * v / top:.3f}">'
                f"<title>{escape(row_label)} {escape(column_labels[c])}: {v:,.0f}</title></rect>"
            )
    for c in range(0, len(column_labels), 3):
        parts.append(
            f'<text class="tick" x="{label_width + c * cell_w + cell_w / 2:.1f}" '
            f'y="{height - 4}" text-anchor="middle">{escape(column_labels[c])}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)
