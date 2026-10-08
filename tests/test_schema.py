import pyarrow as pa

from nyc_taxi_lake.schema import YELLOW_TRIP_SCHEMA, conform


def test_conform_renames_casts_and_fills_missing() -> None:
    legacy = pa.table(
        {
            "VendorID": pa.array([1, 2], pa.int64()),
            "Airport_fee": pa.array([1.75, 0.0]),
            "PULocationID": pa.array([132, 161], pa.int64()),
            "unexpected_column": pa.array(["x", "y"]),
        }
    )
    out = conform(legacy)
    assert out.schema == YELLOW_TRIP_SCHEMA
    assert out.column("airport_fee").to_pylist() == [1.75, 0.0]
    assert out.column("PULocationID").type == pa.int32()
    assert out.column("fare_amount").null_count == 2
    assert "unexpected_column" not in out.column_names
