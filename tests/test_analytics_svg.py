import re
import xml.etree.ElementTree as ET

import pytest

from nyc_taxi_lake.analytics.svg import (
    compact,
    heatmap,
    horizontal_bars,
    line_chart,
    nice_ceiling,
    stacked_bars,
)

SVG = "{http://www.w3.org/2000/svg}"


def parse(svg: str) -> ET.Element:
    # Well-formed XML is the contract: the page embeds the string as-is.
    return ET.fromstring(svg)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, 1.0), (7, 10.0), (12, 20.0), (240, 250.0), (251, 500.0), (666, 1000.0), (1000, 1000.0)],
)
def test_axis_maximum_rounds_up_to_a_readable_value(value: float, expected: float) -> None:
    assert nice_ceiling(value) == expected


def test_compact_labels() -> None:
    assert compact(950) == "950"
    assert compact(1250) == "1.25k"
    assert compact(408_951.76) == "409k"
    assert compact(3_400_000) == "3.4M"


def test_line_chart_draws_one_point_per_value() -> None:
    root = parse(line_chart(["d1", "d2", "d3"], [10, 20, 15], label="Trips per day"))
    assert root.get("aria-label") == "Trips per day"
    points = root.find(f"{SVG}polyline").get("points").split()  # type: ignore[union-attr]
    assert len(points) == 3
    # The highest value sits highest on the page, that is at the smallest y.
    ys = [float(p.split(",")[1]) for p in points]
    assert ys.index(min(ys)) == 1


def test_stacked_bars_stack_series_to_the_total() -> None:
    root = parse(
        stacked_bars(
            ["Jan", "Feb"],
            [("Fares", [60, 30]), ("Tips", [40, 20])],
            label="Revenue",
            height=212,  # a 172-unit plot area once the margins are removed
        )
    )
    rects = root.findall(f"{SVG}rect")
    assert [r.get("class") for r in rects] == ["s0", "s1", "s0", "s1"]
    # Jan totals 100, the axis maximum, so its segments fill the plot area exactly.
    jan = sum(float(r.get("height", 0)) for r in rects[:2])
    assert jan == pytest.approx(172, abs=0.2)


def test_series_length_must_match_the_labels() -> None:
    with pytest.raises(ValueError, match="'Tips' has 1 values for 2 bars"):
        stacked_bars(["Jan", "Feb"], [("Fares", [1, 2]), ("Tips", [1])], label="x")
    with pytest.raises(ValueError, match="2 labels for 1 values"):
        line_chart(["a", "b"], [1], label="x")


def test_horizontal_bars_scale_to_the_largest_value() -> None:
    root = parse(horizontal_bars(["A", "B"], [200, 100], label="Zones", width=704))
    widths = [float(r.get("width", 0)) for r in root.findall(f"{SVG}rect")]
    assert widths == [400.0, 200.0]


def test_heatmap_opacity_tracks_the_value() -> None:
    root = parse(heatmap(["Mon"], ["0", "1"], [[0, 50]], label="Demand"))
    opacities = [float(r.get("fill-opacity", 0)) for r in root.findall(f"{SVG}rect")]
    assert opacities == [pytest.approx(0.06), pytest.approx(1.0)]
    with pytest.raises(ValueError, match="one column per column label"):
        heatmap(["Mon"], ["0", "1"], [[1]], label="x")


def test_labels_from_the_data_are_escaped() -> None:
    svg = horizontal_bars(['<script>"x"</script> & co'], [1], label="a<b")
    assert "<script>" not in svg
    parse(svg)
    assert re.search(r"&lt;script&gt;", svg)


def test_empty_series_still_render() -> None:
    parse(line_chart([], [], label="empty"))
    parse(stacked_bars([], [], label="empty"))
    parse(horizontal_bars([], [], label="empty"))
