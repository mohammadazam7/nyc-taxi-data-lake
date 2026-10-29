import json
import re
from html.parser import HTMLParser
from typing import Any

import pytest

from nyc_taxi_lake.analytics.explorer import embed_json, payload, render
from nyc_taxi_lake.analytics.results import AnalyticsReport, QueryResult


class Scripts(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.scripts: list[str] = []
        self._in_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        self._in_script = tag == "script"
        if tag == "script":
            assert not dict(attrs).get("src"), "scripts must be inline"

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_script = False

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self.scripts.append(data)


def embedded(html: str) -> dict[str, Any]:
    match = re.search(r"const REPORT = (.*?);\n", html)
    assert match, "report data not found in the page"
    data: dict[str, Any] = json.loads(match.group(1))
    return data


def test_page_is_self_contained(analytics_report: AnalyticsReport) -> None:
    html = render(analytics_report)
    parser = Scripts()
    parser.feed(html)
    assert parser.tags.count("script") == 1
    assert "link" not in parser.tags
    assert "http://" not in html and "https://" not in html
    assert "__DATA__" not in html and "__TITLE__" not in html


def test_report_round_trips_through_the_page(analytics_report: AnalyticsReport) -> None:
    data = embedded(render(analytics_report, source_note="Synthetic sample data."))
    assert data["source_note"] == "Synthetic sample data."
    data.pop("source_note")
    assert data == analytics_report.to_dict()


def test_title_names_the_taxi_type_and_range(analytics_report: AnalyticsReport) -> None:
    assert "<title>NYC Yellow taxi explorer, 2024-01 to 2024-02</title>" in render(analytics_report)


def test_script_closing_text_in_data_cannot_end_the_script() -> None:
    hostile = {"zone": "</script><script>alert(1)</script>", "name": "Café"}
    text = embed_json(hostile)
    assert "</" not in text
    assert text.isascii()
    assert json.loads(text) == hostile


def test_report_missing_a_result_is_rejected(analytics_report: AnalyticsReport) -> None:
    partial = AnalyticsReport(
        analytics_report.taxi_type,
        analytics_report.start,
        analytics_report.end,
        tuple(r for r in analytics_report.results if r.name != "payment_mix"),
    )
    with pytest.raises(ValueError, match="payment_mix"):
        payload(partial)


def test_extra_results_are_passed_through(analytics_report: AnalyticsReport) -> None:
    extra = QueryResult.from_records("tolls_by_zone", ["zone_id", "tolls"], [(1, 2.5)])
    report = AnalyticsReport(
        analytics_report.taxi_type,
        analytics_report.start,
        analytics_report.end,
        (*analytics_report.results, extra),
    )
    names = [r["name"] for r in embedded(render(report))["results"]]
    assert "tolls_by_zone" in names
