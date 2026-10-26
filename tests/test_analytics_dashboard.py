from html.parser import HTMLParser

import pytest

from nyc_taxi_lake.analytics.dashboard import render
from nyc_taxi_lake.analytics.results import AnalyticsReport, QueryResult


def report() -> AnalyticsReport:
    q = QueryResult.from_records
    return AnalyticsReport(
        "yellow",
        "2024-01",
        "2024-02",
        (
            q(
                "monthly_revenue",
                [
                    "year",
                    "month",
                    "trips",
                    "revenue",
                    "fares",
                    "tips",
                    "other_charges",
                    "avg_revenue_per_trip",
                ],
                [
                    (2024, 1, 30, 600.0, 420.0, 60.0, 120.0, 20.0),
                    (2024, 2, 10, 200.0, 140.0, 20.0, 40.0, 20.0),
                ],
            ),
            q(
                "daily_trips",
                ["calendar_date", "trips", "revenue", "avg_distance_mi"],
                [("2024-01-01", 30, 600.0, 2.1), ("2024-02-01", 10, 200.0, 2.4)],
            ),
            q(
                "hourly_demand",
                ["day_of_week", "pickup_hour", "trips"],
                [(1, 8, 30), (4, 23, 10)],
            ),
            q(
                "busiest_pickup_zones",
                ["zone_id", "zone_name", "borough", "trips", "revenue"],
                [
                    (132, "JFK Airport", "Queens", 25, 500.0),
                    (7, "Astoria <&>", "Queens", 15, 300.0),
                ],
            ),
            q(
                "payment_mix",
                ["payment_type_id", "payment_type_name", "trips", "revenue", "tip_rate"],
                [(1, "Credit card", 30, 650.0, 0.19), (2, "Cash", 10, 150.0, None)],
            ),
        ),
    )


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


def test_page_is_self_contained() -> None:
    html = render(report())
    tags = parsed(html).tags
    assert "script" not in tags
    assert "link" not in tags
    assert "http://" not in html.replace("http://www.w3.org/2000/svg", "")
    assert "https://" not in html
    assert tags.count("svg") == 4  # revenue, daily, heatmap, zones; payments is a table


def test_summary_tiles_aggregate_the_monthly_rows() -> None:
    text = " ".join(parsed(render(report())).text)
    assert "NYC Yellow taxi trips, 2024-01 to 2024-02" in text
    assert "$800" in text  # revenue
    assert "$20.00" in text  # revenue per trip, 800 / 40
    assert "14.3%" in text  # tips over fares, 80 / 560


def test_payment_table_shows_shares_and_missing_tip_rates() -> None:
    text = parsed(render(report())).text
    assert "75.0%" in text  # card share of trips
    assert "19.0%" in text
    assert "n/a" in text  # cash tip rate is NULL when fares sum to zero


def test_data_values_are_escaped() -> None:
    html = render(report())
    assert "Astoria &lt;&amp;&gt;" in html
    assert "Astoria <&>" not in html


def test_source_note_is_shown_when_given() -> None:
    html = render(report(), source_note="Synthetic sample data.")
    assert "Synthetic sample data." in html


def test_missing_query_results_are_an_error() -> None:
    partial = AnalyticsReport("yellow", "2024-01", "2024-01", report().results[:1])
    with pytest.raises(KeyError, match="daily_trips"):
        render(partial)
