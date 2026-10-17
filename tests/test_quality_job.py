from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from nyc_taxi_lake.cli import build_parser, main
from nyc_taxi_lake.config import Settings
from nyc_taxi_lake.ingest.raw_zone import write_partition
from nyc_taxi_lake.ingest.sample import generate_month
from nyc_taxi_lake.ingest.zone_lookup import write_sample_lookup
from nyc_taxi_lake.months import Month
from nyc_taxi_lake.quality.report import QualityReport
from nyc_taxi_lake.quality.spec import NullRate, QuarantineRate

if TYPE_CHECKING:
    from pyspark.sql import SparkSession

JAN = Month(2024, 1)


class RecordingSink:
    def __init__(self) -> None:
        self.reports: list[QualityReport] = []

    def send(self, report: QualityReport) -> None:
        self.reports.append(report)


def test_quality_parser_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NYC_LAKE_ALERT_SINK", raising=False)
    args = build_parser().parse_args(["quality", "2024-01"])
    assert (args.alert_sink, args.fail_on, args.suite) == ("log", "error", None)

    monkeypatch.setenv("NYC_LAKE_ALERT_SINK", "sns")
    monkeypatch.setenv("NYC_LAKE_SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:1:t")
    args = build_parser().parse_args(["quality", "2024-01"])
    assert (args.alert_sink, args.sns_topic_arn) == ("sns", "arn:aws:sns:us-east-1:1:t")


@pytest.mark.spark
def test_report_is_written_every_run_and_alerts_only_on_breach(
    spark: SparkSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nyc_taxi_lake.clean.job import clean_month
    from nyc_taxi_lake.model.job import model_month, zone_lookup_path
    from nyc_taxi_lake.quality.job import check_month

    monkeypatch.setenv("NYC_LAKE_ROOT", str(tmp_path))
    settings = Settings.from_env()
    write_partition(generate_month(JAN, rows=800), settings.raw_root, "yellow", JAN, "t")
    clean_month(spark, settings, JAN)
    write_sample_lookup(zone_lookup_path(settings))
    model_month(spark, settings, JAN)
    sink = RecordingSink()

    healthy = [NullRate("trip_id", "error", "fact_trips", "trip_id", 0.0)]
    report = check_month(spark, settings, JAN, healthy, sink)
    assert report.status.value == "pass"
    assert sink.reports == []
    saved = json.loads((tmp_path / "quality" / "yellow" / "2024-01.json").read_text())
    assert saved["status"] == "pass"

    strict = [*healthy, QuarantineRate("no_rejects", "error", 0.0)]
    report = check_month(spark, settings, JAN, strict, sink)
    assert report.status.value == "fail"
    assert [r.month for r in sink.reports] == ["2024-01"]
    saved = json.loads((tmp_path / "quality" / "yellow" / "2024-01.json").read_text())
    assert [r["name"] for r in saved["results"] if r["status"] == "fail"] == ["no_rejects"]


@pytest.mark.spark
def test_cli_exit_code_follows_fail_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pytest.importorskip("pyspark", reason="install the [spark] extra to run Spark tests")
    monkeypatch.setenv("NYC_LAKE_ROOT", str(tmp_path))
    main(["ingest", "2024-01", "--sample", "--sample-rows", "800"])
    main(["clean", "2024-01", "--master", "local[2]"])
    main(["model", "2024-01", "--sample-zones", "--master", "local[2]"])
    capsys.readouterr()

    assert main(["quality", "2024-01", "--master", "local[2]"]) == 0
    assert capsys.readouterr().out.startswith("2024-01  pass")

    suite = tmp_path / "strict.toml"
    suite.write_text('[[check]]\nkind = "quarantine_rate"\nmax = 0.0\nseverity = "warn"\n')
    args = ["quality", "2024-01", "--suite", str(suite), "--master", "local[2]"]
    assert main(args) == 0
    assert main([*args, "--fail-on", "warn"]) == 1
    assert "1 warned" in capsys.readouterr().out
