#!/usr/bin/env python3
"""Validate the materialized monthly research universe invariants."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    release = Path(args.release).resolve()
    r = str(release).replace("'", "''")
    connection = duckdb.connect()
    try:
        metrics = {
            "duplicate_month_security_rows": connection.execute(f"""
              SELECT COUNT(*) FROM (
                SELECT date, security_id, COUNT(*) AS n
                FROM read_parquet('{r}/research_universe_monthly.parquet')
                GROUP BY 1, 2 HAVING COUNT(*) > 1
              )
            """).fetchone()[0],
            "non_ordinary_rows": connection.execute(f"SELECT COUNT(*) FROM read_parquet('{r}/research_universe_monthly.parquet') WHERE instrument_type <> 'ORDINARY_EQUITY'").fetchone()[0],
            "future_listing_rows": connection.execute(f"""
              SELECT COUNT(*) FROM read_parquet('{r}/research_universe_monthly.parquet') u
              JOIN (SELECT security_id, MIN(CAST(date AS DATE)) AS first_seen FROM read_parquet('{r}/daily_prices_raw.parquet') GROUP BY security_id) p USING (security_id)
              WHERE CAST(u.date AS DATE) < p.first_seen
            """).fetchone()[0],
            "non_calendar_dates": connection.execute(f"""
              SELECT COUNT(DISTINCT u.date) FROM read_parquet('{r}/research_universe_monthly.parquet') u
              LEFT JOIN read_parquet('{r}/trading_calendar.parquet') c ON CAST(u.date AS DATE) = CAST(c.date AS DATE)
              WHERE c.date IS NULL
            """).fetchone()[0],
            "liquid_predicate_failures": connection.execute(f"""
              SELECT COUNT(*) FROM read_parquet('{r}/research_universe_monthly.parquet')
              WHERE NSE_BROAD_LIQUID_PIT_V1_eligible AND NOT (
                instrument_type = 'ORDINARY_EQUITY' AND trading_status = 'ACTIVE_TRADING'
                AND research_identity_ok AND price_adjustment_ok AND price >= 20
                AND listing_age_sessions >= 272 AND positive_volume_days_60 >= 40
                AND median_traded_value_60 >= 5000000
              )
            """).fetchone()[0],
        }
    finally:
        connection.close()
    metrics["status"] = "PASS" if not any(metrics.values()) else "FAIL"
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(metrics, sort_keys=True))
    if metrics["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
