#!/usr/bin/env python3
"""Build the bounded, point-in-time research universe from a published release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb


def q(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--start", default="2013-01-01")
    parser.add_argument("--end")
    args = parser.parse_args()
    release = Path(args.release)
    out = q(release)
    start = args.start
    end_clause = f"AND CAST(a.date AS DATE) <= DATE '{args.end}'" if args.end else ""
    monthly = q(release / "research_universe_monthly.parquet")
    required = q(release / "required_research_security.parquet")
    query = f"""
    COPY (
      WITH month_end AS (
        SELECT DATE_TRUNC('month', CAST(date AS DATE)) AS month,
               MAX(CAST(date AS DATE)) AS date
        FROM read_parquet('{out}/trading_calendar.parquet')
        WHERE CAST(date AS DATE) >= DATE '{start}'
        GROUP BY 1
      ),
      identity_checks AS (
        SELECT security_id, COUNT(*) AS master_rows,
               COUNT(DISTINCT listing_episode_id) AS episode_count,
               COUNT(DISTINCT series) AS series_count
        FROM read_parquet('{out}/security_master.parquet')
        GROUP BY security_id
      ),
      base AS (
        SELECT CAST(a.date AS DATE) AS date,
          a.security_id, a.listing_episode_id, a.symbol_at_date,
          a.instrument_type, m.identity_quality, a.company_name, a.isin,
          a.trading_status, a.observation_status, a.active,
          f.price, f.history_sessions, f.observed_history_sessions,
          f.listing_age_sessions, f.listing_age_calendar_days,
          f.positive_volume_days_60, f.median_traded_value_60,
          f.median_traded_value_126, f.average_traded_value_60,
          f.absent_observation_days_60, f.zero_volume_days_60,
          f.liquidity_rank_126, f.liquidity_percentile_126,
          f.liquidity_bucket_126,
          CASE
            WHEN m.identity_quality IN ('OFFICIAL_EXCHANGE_IDENTITY', 'MULTI_SOURCE_VERIFIED', 'RECONSTRUCTED_HIGH_CONFIDENCE', 'RECONSTRUCTED_TRADING_IDENTITY')
              THEN m.identity_quality
            WHEN m.identity_quality IN ('PARTIAL', 'SINGLE_OFFICIAL_SOURCE') AND i.master_rows = 1 AND i.episode_count = 1 AND i.series_count = 1
              THEN 'RECONSTRUCTED_TRADING_IDENTITY'
            ELSE m.identity_quality
          END AS research_identity_quality,
          CASE
            WHEN m.identity_quality IN ('OFFICIAL_EXCHANGE_IDENTITY', 'MULTI_SOURCE_VERIFIED', 'RECONSTRUCTED_HIGH_CONFIDENCE', 'RECONSTRUCTED_TRADING_IDENTITY') THEN TRUE
            WHEN m.identity_quality IN ('PARTIAL', 'SINGLE_OFFICIAL_SOURCE') AND i.master_rows = 1 AND i.episode_count = 1 AND i.series_count = 1 THEN TRUE
            ELSE FALSE
          END AS research_identity_ok,
          CASE
            WHEN a.instrument_type = 'ORDINARY_EQUITY' THEN 'OFFICIAL_REFERENCE'
            ELSE 'EXPLICIT_EXCHANGE_MARKER'
          END AS instrument_type_quality,
          CASE WHEN a.trading_status = 'ACTIVE_TRADING' THEN 'OBSERVED_TRADING_RECORD' ELSE 'STATUS_EXCLUDED' END AS status_quality
        FROM read_parquet('{out}/active_universe_daily.parquet') a
        JOIN read_parquet('{out}/liquidity_features.parquet') f
          ON f.security_id = a.security_id AND CAST(f.date AS DATE) = CAST(a.date AS DATE)
        LEFT JOIN read_parquet('{out}/security_master.parquet') m
          ON m.security_id = a.security_id
        LEFT JOIN identity_checks i ON i.security_id = a.security_id
        WHERE CAST(a.date AS DATE) >= DATE '{start}' {end_clause}
          AND a.active
      ),
      ranked AS (
        SELECT b.*, me.month,
          ROW_NUMBER() OVER (PARTITION BY b.date ORDER BY b.median_traded_value_126 DESC NULLS LAST, b.security_id) AS rank_126,
          CASE WHEN b.instrument_type = 'ORDINARY_EQUITY'
             AND b.trading_status = 'ACTIVE_TRADING'
             AND b.research_identity_ok
             AND b.price >= 20
             AND b.listing_age_sessions >= 272
             AND b.positive_volume_days_60 >= 40
             AND b.median_traded_value_60 >= 5000000
            THEN TRUE ELSE FALSE END AS liquid_v1_eligible
        FROM base b
        JOIN month_end me ON me.date = b.date
        WHERE b.instrument_type = 'ORDINARY_EQUITY'
          AND b.trading_status = 'ACTIVE_TRADING'
      )
      SELECT r.*,
        r.rank_126 <= 500 AS top500_liquidity,
        r.rank_126 <= 750 AS top750_liquidity,
        r.rank_126 <= 1000 AS top1000_liquidity,
        r.liquid_v1_eligible AS NSE_BROAD_LIQUID_PIT_V1_eligible,
        'LIQUID_V1' AS profile_id,
        '1' AS profile_version,
        CASE WHEN r.liquid_v1_eligible THEN 'ELIGIBLE' ELSE 'EXCLUDED' END AS eligibility_result
      FROM ranked r
    ) TO '{monthly}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 25000)
    """
    connection = duckdb.connect()
    try:
        connection.execute("PRAGMA threads=4")
        connection.execute(query)
        connection.execute(f"""
        COPY (
          SELECT security_id,
                 MIN(date) AS first_research_date,
                 MAX(date) AS last_research_date,
                 MAX(CASE WHEN liquid_v1_eligible THEN 1 ELSE 0 END)::BOOLEAN AS enters_liquid_v1,
                 MAX(CASE WHEN top750_liquidity THEN 1 ELSE 0 END)::BOOLEAN AS enters_top750,
                 MAX(rank_126) FILTER (WHERE rank_126 IS NOT NULL) AS worst_rank_126,
                 MIN(research_identity_quality) AS research_identity_quality
          FROM read_parquet('{monthly}')
          GROUP BY security_id
          HAVING enters_liquid_v1 OR enters_top750
        ) TO '{required}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """)
        monthly_count = connection.execute(f"SELECT COUNT(*) FROM read_parquet('{monthly}')").fetchone()[0]
        required_count = connection.execute(f"SELECT COUNT(*) FROM read_parquet('{required}')").fetchone()[0]
    finally:
        connection.close()
    print(json.dumps({"monthly_rows": monthly_count, "required_research_securities": required_count}, sort_keys=True))


if __name__ == "__main__":
    main()
