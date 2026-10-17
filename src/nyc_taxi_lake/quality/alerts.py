"""Where quality breaches are sent.

Locally a breach is a log line. In AWS it is a message on an SNS topic, which fans out to
email or chat. Both implement :class:`AlertSink`, so the job does not care which one it
has.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from nyc_taxi_lake.quality.report import QualityReport, Status

log = logging.getLogger(__name__)

SNS_SUBJECT_LIMIT = 100
# SNS caps a message at 256 KiB; leave room for the envelope.
SNS_MESSAGE_LIMIT = 250_000


def _size(text: str) -> int:
    return len(text.encode())


class AlertSink(Protocol):
    def send(self, report: QualityReport) -> None: ...


def subject(report: QualityReport) -> str:
    n = len(report.breaches)
    text = (
        f"[nyc-lake] {report.status.value.upper()}: {report.taxi_type} {report.month}, "
        f"{n} check{'s' if n != 1 else ''} breached"
    )
    return text[:SNS_SUBJECT_LIMIT]


def summary_lines(report: QualityReport) -> list[str]:
    return [
        f"{r.status.value.upper():4}  {r.name}: observed {r.observed}, expected {r.threshold}"
        + (f" ({r.detail})" if r.detail else "")
        for r in report.breaches
    ]


class LogSink:
    """Write each breach to the log; errors at ERROR level, warnings at WARNING."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or log

    def send(self, report: QualityReport) -> None:
        level = logging.ERROR if report.status is Status.FAIL else logging.WARNING
        self.logger.log(level, subject(report))
        for line in summary_lines(report):
            self.logger.log(level, "  %s", line)


class SnsSink:
    """Publish a breach summary to an SNS topic.

    The message body is the readable summary followed by the breached results as JSON,
    so an email subscriber can read it and a Lambda subscriber can parse it. A
    ``status`` message attribute lets subscriptions filter, e.g. page only on ``fail``.
    """

    def __init__(self, topic_arn: str, client: Any | None = None) -> None:
        if not topic_arn.startswith("arn:"):
            raise ValueError(f"expected an SNS topic ARN, got {topic_arn!r}")
        self.topic_arn = topic_arn
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                import boto3
            except ImportError as exc:  # pragma: no cover - depends on the install
                raise RuntimeError("the SNS alert sink needs the [aws] extra") from exc
            self._client = boto3.client("sns")
        return self._client

    def message(self, report: QualityReport) -> str:
        """Summary lines, then the breaches as JSON, kept under the SNS size limit.

        If everything does not fit, the JSON is dropped first and then summary lines,
        with a pointer to the full report that the job always writes to the lake.
        """
        results = report.to_dict()["results"]
        breaches = [r for r in results if r["status"] != Status.PASS.value]
        payload = json.dumps(breaches, indent=2)
        lines = summary_lines(report)
        full = "\n".join([subject(report), "", *lines, "", "breaches:", payload])
        if _size(full) <= SNS_MESSAGE_LIMIT:
            return full

        kept: list[str] = [subject(report), ""]
        budget = SNS_MESSAGE_LIMIT - 200
        for i, line in enumerate(lines):
            if _size("\n".join([*kept, line])) > budget:
                kept.append(f"... and {len(lines) - i} more")
                break
            kept.append(line)
        kept += ["", "Truncated to fit SNS; the full JSON report is in the lake."]
        return "\n".join(kept)

    def send(self, report: QualityReport) -> None:
        self.client.publish(
            TopicArn=self.topic_arn,
            Subject=subject(report),
            Message=self.message(report),
            MessageAttributes={
                "status": {"DataType": "String", "StringValue": report.status.value},
                "month": {"DataType": "String", "StringValue": report.month},
            },
        )
        log.info("sent %s alert for %s to %s", report.status.value, report.month, self.topic_arn)


def make_sink(kind: str, topic_arn: str | None = None) -> AlertSink:
    if kind == "log":
        return LogSink()
    if kind == "sns":
        if not topic_arn:
            raise ValueError("the sns sink needs a topic ARN (--sns-topic-arn)")
        return SnsSink(topic_arn)
    raise ValueError(f"unknown alert sink {kind!r}; expected 'log' or 'sns'")
