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
            "non_active_trading_rows": connection.execute(f"""
              SELECT COUNT(*) FROM read_parquet('{r}/research_universe_monthly.parquet')
              WHERE COALESCE(active, FALSE) <> TRUE
                 OR trading_status IS DISTINCT FROM 'ACTIVE_TRADING'
            """).fetchone()[0],
            "missing_quality_fields": connection.execute(f"""
              SELECT COUNT(*) FROM read_parquet('{r}/research_universe_monthly.parquet')
              WHERE identity_quality IS NULL
                 OR research_identity_ok IS NULL
                 OR price_adjustment_quality IS NULL
                 OR price_adjustment_ok IS NULL
                 OR status_quality IS NULL
            """).fetchone()[0],
            "required_scope_quality_failures": connection.execute(f"""
              SELECT COUNT(*) FROM read_parquet('{r}/research_universe_monthly.parquet')
              WHERE (COALESCE(LIQUID_V1_eligible, NSE_BROAD_LIQUID_PIT_V1_eligible, FALSE)
                     OR COALESCE(top750_liquidity, FALSE))
                AND (research_identity_ok IS DISTINCT FROM TRUE
                     OR price_adjustment_ok IS DISTINCT FROM TRUE)
            """).fetchone()[0],
            "required_scope_missing_research_fields": connection.execute(f"""
              SELECT COUNT(*) FROM read_parquet('{r}/research_universe_monthly.parquet')
              WHERE (COALESCE(LIQUID_V1_eligible, NSE_BROAD_LIQUID_PIT_V1_eligible, FALSE)
                     OR COALESCE(top750_liquidity, FALSE))
                AND (
                  date IS NULL
                  OR security_id IS NULL
                  OR listing_episode_id IS NULL
                  OR symbol_at_date IS NULL
                  OR instrument_type IS NULL
                  OR identity_quality IS NULL
                  OR price IS NULL
                  OR history_sessions IS NULL
                  OR positive_volume_days_60 IS NULL
                  OR median_traded_value_60 IS NULL
                  OR median_traded_value_126 IS NULL
                  OR liquidity_rank_126 IS NULL
                  OR liquidity_percentile IS NULL
                  OR LIQUID_V1_eligible IS NULL
                  OR research_identity_ok IS NULL
                  OR price_adjustment_quality IS NULL
                  OR status_quality IS NULL
                )
            """).fetchone()[0],
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
            "artifact_alias_failures": connection.execute(f"""
              SELECT COUNT(*) FROM read_parquet('{r}/research_universe_monthly.parquet')
              WHERE COALESCE(LIQUID_V1_eligible, FALSE) <> COALESCE(NSE_BROAD_LIQUID_PIT_V1_eligible, FALSE)
                 OR liquidity_percentile IS DISTINCT FROM liquidity_percentile_126
            """).fetchone()[0],
            "eligible_profile_metadata_failures": connection.execute(f"""
              SELECT COUNT(*) FROM read_parquet('{r}/research_universe_monthly.parquet')
              WHERE NSE_BROAD_LIQUID_PIT_V1_eligible AND NOT (
                profile_id = 'NSE_BROAD_LIQUID_PIT_V1'
                AND profile_version = 'LIQUID_V1'
                AND CAST(as_of_date AS DATE) = CAST(date AS DATE)
                AND eligibility_result = 'ELIGIBLE'
                AND eligibility_reason_codes = 'PASSED_LIQUID_V1'
              )
            """).fetchone()[0],
            "excluded_profile_metadata_failures": connection.execute(f"""
              SELECT COUNT(*) FROM read_parquet('{r}/research_universe_monthly.parquet')
              WHERE NOT NSE_BROAD_LIQUID_PIT_V1_eligible AND (
                profile_id <> 'NSE_BROAD_LIQUID_PIT_V1'
                OR profile_version <> 'LIQUID_V1'
                OR CAST(as_of_date AS DATE) <> CAST(date AS DATE)
                OR eligibility_result <> 'EXCLUDED'
                OR eligibility_reason_codes IS NULL
              )
            """).fetchone()[0],
            "top_liquidity_flag_failures": connection.execute(f"""
              SELECT COUNT(*) FROM read_parquet('{r}/research_universe_monthly.parquet')
              WHERE COALESCE(top500_liquidity, FALSE) <> COALESCE(rank_126 <= 500, FALSE)
                 OR COALESCE(top750_liquidity, FALSE) <> COALESCE(rank_126 <= 750, FALSE)
                 OR COALESCE(top1000_liquidity, FALSE) <> COALESCE(rank_126 <= 1000, FALSE)
                 OR (COALESCE(top500_liquidity, FALSE) AND NOT COALESCE(top750_liquidity, FALSE))
                 OR (COALESCE(top750_liquidity, FALSE) AND NOT COALESCE(top1000_liquidity, FALSE))
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
