"""Run load statements on Redshift Serverless through the Redshift Data API.

The Data API needs no driver, no open port and no password: it authenticates with the
caller's IAM identity and runs SQL over HTTPS. ``batch_execute_statement`` runs its
statements as one transaction, so a failed ``COPY`` rolls the whole month back.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from typing import Any

log = logging.getLogger(__name__)

RUNNING = {"SUBMITTED", "PICKED", "STARTED"}


class LoadError(RuntimeError):
    """The batch failed or was aborted; Redshift rolled it back."""


class DataApiRunner:
    def __init__(
        self,
        workgroup: str,
        database: str,
        *,
        client: Any = None,
        poll_seconds: float = 2.0,
        timeout_seconds: float = 30 * 60,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.workgroup = workgroup
        self.database = database
        self._client = client
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds
        self._sleep = sleep
        self._clock = clock

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                import boto3
            except ImportError as exc:  # pragma: no cover - depends on the environment
                raise RuntimeError("loading into Redshift needs the [aws] extra") from exc
            self._client = boto3.client("redshift-data")
        return self._client

    def run(self, statements: Sequence[str]) -> str:
        """Run ``statements`` as one transaction and wait for it. Returns the statement id."""
        if not statements:
            raise ValueError("nothing to run")
        response = self.client.batch_execute_statement(
            WorkgroupName=self.workgroup, Database=self.database, Sqls=list(statements)
        )
        statement_id: str = response["Id"]
        log.info("submitted %d statements as %s", len(statements), statement_id)

        deadline = self._clock() + self.timeout_seconds
        while True:
            status = self.client.describe_statement(Id=statement_id)
            state = status["Status"]
            if state == "FINISHED":
                return statement_id
            if state not in RUNNING:
                raise LoadError(f"{statement_id} {state}: {status.get('Error', 'no error given')}")
            if self._clock() > deadline:
                self.client.cancel_statement(Id=statement_id)
                raise LoadError(f"{statement_id} still {state} after {self.timeout_seconds:.0f}s")
            self._sleep(self.poll_seconds)
