from html.parser import HTMLParser

import pytest

from nyc_taxi_lake.analytics.dashboard import provenance_note, render
from nyc_taxi_lake.analytics.results import AnalyticsReport


class Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)

    def handle_data(self, data: str) -> None:
        self.text.append(data)


def parsed(html: str) -> Collector:
    collector = Collector()
    collector.feed(html)
    return collector


def test_page_is_self_contained(analytics_report: AnalyticsReport) -> None:
    html = render(analytics_report)
    tags = parsed(html).tags
    assert "script" not in tags
    assert "link" not in tags
    assert "http://" not in html.replace("http://www.w3.org/2000/svg", "")
    assert "https://" not in html
    assert tags.count("svg") == 4  # revenue, daily, heatmap, zones; payments is a table


def test_summary_tiles_aggregate_the_monthly_rows(analytics_report: AnalyticsReport) -> None:
    text = " ".join(parsed(render(analytics_report)).text)
    assert "NYC Yellow taxi trips, 2024-01 to 2024-02" in text
    assert "$800" in text  # revenue
    assert "$20.00" in text  # revenue per trip, 800 / 40
    assert "14.3%" in text  # tips over fares, 80 / 560


def test_payment_table_shows_shares_and_missing_tip_rates(
    analytics_report: AnalyticsReport,
) -> None:
    text = parsed(render(analytics_report)).text
    assert "75.0%" in text  # card share of trips
    assert "19.0%" in text
    assert "n/a" in text  # cash tip rate is NULL when fares sum to zero


def test_data_values_are_escaped(analytics_report: AnalyticsReport) -> None:
    html = render(analytics_report)
    assert "Astoria &lt;&amp;&gt;" in html
    assert "Astoria <&>" not in html


def test_source_note_is_shown_when_given(analytics_report: AnalyticsReport) -> None:
    html = render(analytics_report, source_note="Synthetic sample data.")
    assert "Synthetic sample data." in html


def test_missing_query_results_are_an_error(analytics_report: AnalyticsReport) -> None:
    partial = AnalyticsReport("yellow", "2024-01", "2024-01", analytics_report.results[:1])
    with pytest.raises(KeyError, match="daily_trips"):
        render(partial)


def test_provenance_note_flags_synthetic_months() -> None:
    synthetic = "synthetic://yellow/2024-01?rows=1000"
    real = "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2024-02.parquet"
    assert provenance_note([]) == ""
    assert provenance_note([synthetic]).startswith("Synthetic sample data")
    assert provenance_note([synthetic, real]) == "1 of 2 months are synthetic sample data."
    assert provenance_note([real]) == "Source: NYC TLC trip record files."
