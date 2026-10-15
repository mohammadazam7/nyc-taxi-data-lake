-- Star schema for the warehouse zone, loaded into Redshift Serverless with COPY ... FORMAT
-- AS PARQUET (milestone 6). Column names and order match the Parquet files that
-- `nyc-lake model` writes, which COPY needs; tests/test_redshift_ddl.py keeps them in step.
--
-- fact_trips has no pickup_date column: in the lake it is the partition directory, not a
-- column in the files, and pickup_date_key carries the same information.
--
-- Redshift does not enforce primary or foreign keys. They are declared because the
-- planner uses them, and the data-quality checks (milestone 4) are what actually
-- guarantee them.
--
-- The dimensions are small, so they are copied to every node (DISTSTYLE ALL) and joins
-- to them never move data. The fact table is sorted by pickup date, which is what almost
-- every query filters on.

CREATE SCHEMA IF NOT EXISTS taxi;

CREATE TABLE IF NOT EXISTS taxi.dim_date (
    date_key        INTEGER     NOT NULL,
    calendar_date   DATE        NOT NULL,
    year            INTEGER     NOT NULL,
    quarter         INTEGER     NOT NULL,
    month           INTEGER     NOT NULL,
    month_name      VARCHAR(9)  NOT NULL,
    day_of_month    INTEGER     NOT NULL,
    day_of_week     INTEGER     NOT NULL,  -- ISO: Monday = 1 ... Sunday = 7
    day_name        VARCHAR(9)  NOT NULL,
    iso_week        INTEGER     NOT NULL,
    is_weekend      BOOLEAN     NOT NULL,
    PRIMARY KEY (date_key)
)
DISTSTYLE ALL
SORTKEY (date_key);

CREATE TABLE IF NOT EXISTS taxi.dim_zone (
    zone_key        BIGINT       NOT NULL,
    zone_id         INTEGER      NOT NULL,
    zone_name       VARCHAR(64)  NOT NULL,
    borough         VARCHAR(32)  NOT NULL,
    service_zone    VARCHAR(32)  NOT NULL,
    PRIMARY KEY (zone_key)
)
DISTSTYLE ALL;

CREATE TABLE IF NOT EXISTS taxi.dim_vendor (
    vendor_key      BIGINT       NOT NULL,
    vendor_id       INTEGER      NOT NULL,
    vendor_name     VARCHAR(64)  NOT NULL,
    PRIMARY KEY (vendor_key)
)
DISTSTYLE ALL;

CREATE TABLE IF NOT EXISTS taxi.dim_rate_code (
    rate_code_key   BIGINT       NOT NULL,
    rate_code_id    INTEGER      NOT NULL,
    rate_code_name  VARCHAR(64)  NOT NULL,
    PRIMARY KEY (rate_code_key)
)
DISTSTYLE ALL;

CREATE TABLE IF NOT EXISTS taxi.dim_payment_type (
    payment_type_key   BIGINT       NOT NULL,
    payment_type_id    INTEGER      NOT NULL,
    payment_type_name  VARCHAR(64)  NOT NULL,
    PRIMARY KEY (payment_type_key)
)
DISTSTYLE ALL;

CREATE TABLE IF NOT EXISTS taxi.fact_trips (
    trip_id                CHAR(64)          NOT NULL,  -- SHA-256 of the raw row, hex
    pickup_date_key        INTEGER           NOT NULL REFERENCES taxi.dim_date (date_key),
    dropoff_date_key       INTEGER           NOT NULL REFERENCES taxi.dim_date (date_key),
    pickup_zone_key        BIGINT            NOT NULL REFERENCES taxi.dim_zone (zone_key),
    dropoff_zone_key       BIGINT            NOT NULL REFERENCES taxi.dim_zone (zone_key),
    vendor_key             BIGINT            NOT NULL REFERENCES taxi.dim_vendor (vendor_key),
    rate_code_key          BIGINT            NOT NULL REFERENCES taxi.dim_rate_code (rate_code_key),
    payment_type_key       BIGINT            NOT NULL REFERENCES taxi.dim_payment_type (payment_type_key),
    pickup_at              TIMESTAMP         NOT NULL,
    dropoff_at             TIMESTAMP         NOT NULL,
    trip_duration_s        INTEGER,
    passenger_count        INTEGER,
    trip_distance_mi       DOUBLE PRECISION,
    store_and_forward      BOOLEAN,
    fare_amount            DECIMAL(10, 2),
    extra_amount           DECIMAL(10, 2),
    mta_tax                DECIMAL(10, 2),
    tip_amount             DECIMAL(10, 2),
    tolls_amount           DECIMAL(10, 2),
    improvement_surcharge  DECIMAL(10, 2),
    congestion_surcharge   DECIMAL(10, 2),
    airport_fee            DECIMAL(10, 2),
    total_amount           DECIMAL(10, 2),
    PRIMARY KEY (trip_id)
)
DISTSTYLE AUTO
SORTKEY (pickup_date_key);
