from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pyspark.sql import SparkSession


@pytest.fixture(scope="session")
def _spark_teardown() -> Iterator[None]:
    yield
    from pyspark.sql import SparkSession

    active = SparkSession.getActiveSession()
    if active is not None:
        active.stop()


@pytest.fixture
def spark(_spark_teardown: None) -> SparkSession:
    """A local session shared by the tests.

    ``getOrCreate`` hands back the running session, so this is cheap after the first
    call. It also starts a new one if an earlier test stopped it, which the CLI does on
    exit (``nyc-lake clean`` owns its session), so test order does not matter.
    """
    pytest.importorskip("pyspark", reason="install the [spark] extra to run Spark tests")
    from nyc_taxi_lake.spark import get_spark

    session = get_spark("nyc-taxi-lake-tests", master="local[2]")
    session.sparkContext.setLogLevel("ERROR")
    return session
