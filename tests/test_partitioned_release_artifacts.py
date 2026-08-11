from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[1]


def test_partitioned_release_artifacts_preserve_rows(tmp_path: Path):
    release = tmp_path / "release"
    release.mkdir()
    table = pa.Table.from_pylist(
        [
            {"date": "2020-01-01", "security_id": "A", "raw_close": 10.0},
            {"date": "2020-01-02", "security_id": "B", "raw_close": 20.0},
            {"date": "2021-01-01", "security_id": "A", "raw_close": 30.0},
        ]
    )
    for name in ("daily_prices_raw.parquet", "daily_prices_adjusted.parquet", "liquidity_features.parquet", "active_universe_daily.parquet"):
        pq.write_table(table, release / name)

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{ROOT / 'src'}{os.pathsep}{env.get('PYTHONPATH', '')}"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/build_partitioned_release_artifacts.py"),
            "--release",
            str(release),
        ],
        check=True,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    manifest = release / "partitioned_artifacts_manifest.json"
    assert manifest.exists()
    connection = duckdb.connect()
    try:
        rows = connection.execute(f"SELECT COUNT(*) FROM read_parquet('{release / 'daily_prices_raw_by_year/**/*.parquet'}')").fetchone()[0]
        years = connection.execute(f"SELECT DISTINCT partition_year FROM read_parquet('{release / 'daily_prices_raw_by_year/**/*.parquet'}') ORDER BY 1").fetchall()
    finally:
        connection.close()
    assert rows == 3
    assert years == [(2020,), (2021,)]
