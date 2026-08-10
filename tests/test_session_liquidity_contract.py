from pathlib import Path
import sys

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq


def test_official_session_window_counts_absent_rows(tmp_path: Path):
    calendar = tmp_path / "calendar.parquet"
    prices = tmp_path / "prices.parquet"
    output = tmp_path / "features.parquet"
    pq.write_table(
        pa.table({"date": ["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-06"]}),
        calendar,
    )
    pq.write_table(
        pa.table({
            "date": ["2020-01-01", "2020-01-03", "2020-01-06"],
            "security_id": ["SEC1"] * 3,
            "listing_episode_id": ["EP1"] * 3,
            "symbol_at_date": ["ABC"] * 3,
            "raw_close": [10.0, 10.0, 10.0],
            "volume": [10, 0, 10],
            "traded_value": [100.0, 0.0, 100.0],
        }),
        prices,
    )
    import subprocess
    subprocess.run(
        [sys.executable, "scripts/rebuild_liquidity_features_duckdb.py", "--prices", str(prices), "--calendar", str(calendar), "--out", str(output)],
        check=True,
    )
    row = duckdb.connect().execute(
        "SELECT * FROM read_parquet(?) WHERE date = '2020-01-06'", [str(output)]
    ).fetchone()
    columns = [item[0] for item in duckdb.connect().execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(output)]).fetchall()]
    values = dict(zip(columns, row))
    assert values["history_sessions"] == 4
    assert values["positive_volume_days_20"] == 2
    assert values["absent_observation_days_20"] == 1
    assert values["liquidity_window_definition"] == "OFFICIAL_NSE_SESSION_WINDOW"
