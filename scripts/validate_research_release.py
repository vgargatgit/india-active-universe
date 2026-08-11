#!/usr/bin/env python3
"""Validate the materialized monthly research universe invariants."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

from india_active_universe.profiles import LIQUID_V1_DEFINITION


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    release = Path(args.release).resolve()
    r = str(release).replace("'", "''")
    price_min = LIQUID_V1_DEFINITION["price_min"]
    listing_age_min = LIQUID_V1_DEFINITION["listing_age_sessions_min"]
    positive_volume_min = LIQUID_V1_DEFINITION["positive_volume_days_60_min"]
    median_value_min = LIQUID_V1_DEFINITION["median_traded_value_60_min"]
    instrument_type = LIQUID_V1_DEFINITION["instrument_type"]
    trading_status = LIQUID_V1_DEFINITION["trading_status"]
    active = "TRUE" if LIQUID_V1_DEFINITION["active"] else "FALSE"
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
            "non_ordinary_rows": connection.execute(f"SELECT COUNT(*) FROM read_parquet('{r}/research_universe_monthly.parquet') WHERE instrument_type <> '{instrument_type}'").fetchone()[0],
            "non_active_trading_rows": connection.execute(f"""
              SELECT COUNT(*) FROM read_parquet('{r}/research_universe_monthly.parquet')
              WHERE COALESCE(active, FALSE) <> {active}
                 OR trading_status IS DISTINCT FROM '{trading_status}'
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
            "top_liquidity_null_metric_failures": connection.execute(f"""
              SELECT COUNT(*) FROM read_parquet('{r}/research_universe_monthly.parquet')
              WHERE (COALESCE(top500_liquidity, FALSE)
                  OR COALESCE(top750_liquidity, FALSE)
                  OR COALESCE(top1000_liquidity, FALSE))
                AND median_traded_value_126 IS NULL
            """).fetchone()[0],
            "required_scope_missing_from_required_artifact": connection.execute(f"""
              WITH monthly_required AS (
                SELECT DISTINCT security_id
                FROM read_parquet('{r}/research_universe_monthly.parquet')
                WHERE COALESCE(LIQUID_V1_eligible, NSE_BROAD_LIQUID_PIT_V1_eligible, FALSE)
                   OR COALESCE(top750_liquidity, FALSE)
              )
              SELECT COUNT(*)
              FROM monthly_required m
              LEFT JOIN read_parquet('{r}/required_research_security.parquet') rrs
                ON m.security_id = rrs.security_id
              WHERE rrs.security_id IS NULL
            """).fetchone()[0],
            "required_artifact_security_without_monthly_scope": connection.execute(f"""
              WITH monthly_required AS (
                SELECT DISTINCT security_id
                FROM read_parquet('{r}/research_universe_monthly.parquet')
                WHERE COALESCE(LIQUID_V1_eligible, NSE_BROAD_LIQUID_PIT_V1_eligible, FALSE)
                   OR COALESCE(top750_liquidity, FALSE)
              )
              SELECT COUNT(*)
              FROM read_parquet('{r}/required_research_security.parquet') rrs
              LEFT JOIN monthly_required m
                ON m.security_id = rrs.security_id
              WHERE m.security_id IS NULL
            """).fetchone()[0],
            "required_artifact_flag_failures": connection.execute(f"""
              WITH monthly_flags AS (
                SELECT security_id,
                       MAX(CASE WHEN COALESCE(LIQUID_V1_eligible, NSE_BROAD_LIQUID_PIT_V1_eligible, FALSE) THEN 1 ELSE 0 END)::BOOLEAN AS enters_liquid_v1,
                       MAX(CASE WHEN COALESCE(top750_liquidity, FALSE) THEN 1 ELSE 0 END)::BOOLEAN AS enters_top750
                FROM read_parquet('{r}/research_universe_monthly.parquet')
                GROUP BY security_id
              )
              SELECT COUNT(*)
              FROM read_parquet('{r}/required_research_security.parquet') rrs
              JOIN monthly_flags m USING (security_id)
              WHERE rrs.enters_liquid_v1 IS DISTINCT FROM m.enters_liquid_v1
                 OR rrs.enters_top750 IS DISTINCT FROM m.enters_top750
            """).fetchone()[0],
            "required_artifact_date_range_failures": connection.execute(f"""
              WITH monthly_ranges AS (
                SELECT security_id,
                       MIN(date) AS first_research_date,
                       MAX(date) AS last_research_date
                FROM read_parquet('{r}/research_universe_monthly.parquet')
                WHERE COALESCE(LIQUID_V1_eligible, NSE_BROAD_LIQUID_PIT_V1_eligible, FALSE)
                   OR COALESCE(top750_liquidity, FALSE)
                GROUP BY security_id
              )
              SELECT COUNT(*)
              FROM read_parquet('{r}/required_research_security.parquet') rrs
              JOIN monthly_ranges m USING (security_id)
              WHERE CAST(rrs.first_research_date AS DATE) IS DISTINCT FROM CAST(m.first_research_date AS DATE)
                 OR CAST(rrs.last_research_date AS DATE) IS DISTINCT FROM CAST(m.last_research_date AS DATE)
            """).fetchone()[0],
            "required_artifact_rank_evidence_failures": connection.execute(f"""
              WITH monthly_ranks AS (
                SELECT security_id,
                       MIN(rank_126) AS best_rank_126,
                       MAX(rank_126) AS worst_rank_126
                FROM read_parquet('{r}/research_universe_monthly.parquet')
                WHERE (COALESCE(LIQUID_V1_eligible, NSE_BROAD_LIQUID_PIT_V1_eligible, FALSE)
                       OR COALESCE(top750_liquidity, FALSE))
                  AND rank_126 IS NOT NULL
                GROUP BY security_id
              )
              SELECT COUNT(*)
              FROM read_parquet('{r}/required_research_security.parquet') rrs
              JOIN monthly_ranks m USING (security_id)
              WHERE rrs.best_rank_126 IS DISTINCT FROM m.best_rank_126
                 OR rrs.worst_rank_126 IS DISTINCT FROM m.worst_rank_126
            """).fetchone()[0],
            "required_artifact_liquidity_evidence_failures": connection.execute(f"""
              WITH monthly_liquidity AS (
                SELECT security_id,
                       MAX(median_traded_value_60) AS max_median_traded_value_60,
                       MAX(median_traded_value_126) AS max_median_traded_value_126,
                       MAX(positive_volume_days_60) AS max_positive_volume_days_60
                FROM read_parquet('{r}/research_universe_monthly.parquet')
                WHERE COALESCE(LIQUID_V1_eligible, NSE_BROAD_LIQUID_PIT_V1_eligible, FALSE)
                   OR COALESCE(top750_liquidity, FALSE)
                GROUP BY security_id
              )
              SELECT COUNT(*)
              FROM read_parquet('{r}/required_research_security.parquet') rrs
              JOIN monthly_liquidity m USING (security_id)
              WHERE rrs.max_median_traded_value_60 IS DISTINCT FROM m.max_median_traded_value_60
                 OR rrs.max_median_traded_value_126 IS DISTINCT FROM m.max_median_traded_value_126
                 OR rrs.max_positive_volume_days_60 IS DISTINCT FROM m.max_positive_volume_days_60
            """).fetchone()[0],
            "required_artifact_identity_quality_failures": connection.execute(f"""
              SELECT COUNT(*)
              FROM read_parquet('{r}/required_research_security.parquet')
              WHERE research_identity_quality NOT IN (
                'OFFICIAL_EXCHANGE_IDENTITY',
                'MULTI_SOURCE_VERIFIED',
                'RECONSTRUCTED_HIGH_CONFIDENCE',
                'RECONSTRUCTED_TRADING_IDENTITY'
              )
                 OR research_identity_quality IS NULL
            """).fetchone()[0],
            "required_artifact_price_adjustment_failures": connection.execute(f"""
              SELECT COUNT(*)
              FROM read_parquet('{r}/required_research_security.parquet')
              WHERE price_adjustment_ok IS DISTINCT FROM TRUE
                 OR price_adjustment_quality IS NULL
                 OR price_adjustment_quality IN ('UNRESOLVED_CORPORATE_ACTION', 'RAW_ONLY_UNKNOWN')
            """).fetchone()[0],
            "required_artifact_status_failures": connection.execute(f"""
              SELECT COUNT(*)
              FROM read_parquet('{r}/required_research_security.parquet')
              WHERE active_trading_ok IS DISTINCT FROM TRUE
                 OR status_quality IS NULL
                 OR status_quality IN ('UNKNOWN_STATUS', 'UNRESOLVED')
            """).fetchone()[0],
            "required_artifact_instrument_classification_failures": connection.execute(f"""
              SELECT COUNT(*)
              FROM read_parquet('{r}/required_research_security.parquet')
              WHERE instrument_type IS DISTINCT FROM '{instrument_type}'
                 OR instrument_type_quality IS NULL
                 OR instrument_type_quality = 'UNRESOLVED'
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
                instrument_type = '{instrument_type}' AND trading_status = '{trading_status}'
                AND research_identity_ok AND price_adjustment_ok AND price >= {price_min}
                AND listing_age_sessions >= {listing_age_min} AND positive_volume_days_60 >= {positive_volume_min}
                AND median_traded_value_60 >= {median_value_min}
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
