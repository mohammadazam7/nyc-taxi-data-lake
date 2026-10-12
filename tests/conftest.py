from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pyspark.sql import SparkSession


@pytest.fixture(scope="session")
def spark() -> Iterator[SparkSession]:
    pytest.importorskip("pyspark", reason="install the [spark] extra to run Spark tests")
    from nyc_taxi_lake.spark import get_spark

    session = get_spark("nyc-taxi-lake-tests", master="local[2]")
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()
