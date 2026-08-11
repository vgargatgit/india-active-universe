import os
import subprocess
import sys
from pathlib import Path

import duckdb

from india_active_universe.profiles import (
    ADJUSTED_PRICE_ARTIFACT,
    LIQUIDITY_ARTIFACT,
    RAW_EXECUTION_PRICE_ARTIFACT,
    TRADING_CALENDAR_ARTIFACT,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "nse_source_eras"


def run_script(name: str, *args: str) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / name), *args],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_real_nse_source_eras_build_to_liquidity_and_adjusted_prices(tmp_path: Path):
    build = tmp_path / "build"
    release = tmp_path / "release"
    events = tmp_path / "corporate_actions.jsonl"
    events.write_text("", encoding="utf-8")

    run_script(
        "build_nse_universe.py",
        "--raw", str(FIXTURE),
        "--out", str(build),
        "--manual-overrides", str(ROOT / "data/reference/manual_identity_overrides.yaml"),
    )
    run_script("publish_parquet.py", "--data", str(build), "--release", str(release))
    run_script("build_trading_calendar.py", "--prices", str(release / RAW_EXECUTION_PRICE_ARTIFACT), "--out", str(release / TRADING_CALENDAR_ARTIFACT))
    run_script("rebuild_liquidity_features_duckdb.py", "--prices", str(release / RAW_EXECUTION_PRICE_ARTIFACT), "--calendar", str(release / TRADING_CALENDAR_ARTIFACT), "--out", str(release / LIQUIDITY_ARTIFACT))
    run_script("apply_corporate_action_adjustments.py", "--prices", str(build / "canonical/daily_prices_raw.jsonl"), "--events", str(events), "--out", str(release / ADJUSTED_PRICE_ARTIFACT))

    connection = duckdb.connect()
    try:
        dates = connection.execute(f"SELECT COUNT(DISTINCT CAST(date AS DATE)) FROM read_parquet('{release / RAW_EXECUTION_PRICE_ARTIFACT}')").fetchone()[0]
        raw_rows = connection.execute(f"SELECT COUNT(*) FROM read_parquet('{release / RAW_EXECUTION_PRICE_ARTIFACT}')").fetchone()[0]
        calendar_rows = connection.execute(f"SELECT COUNT(*) FROM read_parquet('{release / TRADING_CALENDAR_ARTIFACT}')").fetchone()[0]
        liquidity_rows = connection.execute(f"SELECT COUNT(*) FROM read_parquet('{release / LIQUIDITY_ARTIFACT}')").fetchone()[0]
        adjusted_rows = connection.execute(f"SELECT COUNT(*) FROM read_parquet('{release / ADJUSTED_PRICE_ARTIFACT}')").fetchone()[0]
    finally:
        connection.close()

    assert dates == 4
    assert raw_rows > 100
    assert calendar_rows == 4
    assert liquidity_rows > 100
    assert adjusted_rows == raw_rows
