# Development image: the nyc-lake CLI with PySpark and a Java runtime, so the whole
# pipeline runs locally without installing Java or Spark on the host.
#
#   docker build -t nyc-lake .
#   docker run --rm -v "$PWD/lake:/lake" nyc-lake run 2024-01 2024-03 --sample --sample-zones
#
# EXTRAS selects the package extras; add dev for the test and lint tools.

FROM python:3.12-slim-bookworm

ARG EXTRAS=spark,aws

# PySpark needs a JVM (17 or later) and ps, which its launcher scripts call.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends openjdk-17-jre-headless procps \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    NYC_LAKE_ROOT=/lake

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install ".[${EXTRAS}]"

RUN useradd --create-home --uid 1000 lake \
    && mkdir /lake \
    && chown lake:lake /lake
USER lake
VOLUME ["/lake"]

ENTRYPOINT ["nyc-lake"]
CMD ["--help"]
