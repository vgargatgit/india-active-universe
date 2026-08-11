#!/usr/bin/env python3
"""Build the bounded, point-in-time research universe from a published release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

from india_active_universe.profiles import LIQUID_V1_DEFINITION


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
    price_min = LIQUID_V1_DEFINITION["price_min"]
    listing_age_min = LIQUID_V1_DEFINITION["listing_age_sessions_min"]
    positive_volume_min = LIQUID_V1_DEFINITION["positive_volume_days_60_min"]
    median_value_min = LIQUID_V1_DEFINITION["median_traded_value_60_min"]
    instrument_type = LIQUID_V1_DEFINITION["instrument_type"]
    trading_status = LIQUID_V1_DEFINITION["trading_status"]
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
               COUNT(DISTINCT series) AS series_count,
               COUNT(DISTINCT isin) AS isin_count
        FROM read_parquet('{out}/security_master.parquet')
        GROUP BY security_id
      ),
      base AS (
        SELECT CAST(a.date AS DATE) AS date,
          a.security_id, a.listing_episode_id, a.symbol_at_date,
          a.instrument_type, m.instrument_type_quality, m.instrument_type_source, m.identity_quality, a.company_name, a.isin,
          COALESCE(s.trading_status, a.trading_status) AS trading_status,
          a.observation_status, a.active,
          f.price, f.history_sessions, f.observed_history_sessions,
          f.listing_age_sessions, f.listing_age_calendar_days,
          f.positive_volume_days_60, f.median_traded_value_60,
          f.median_traded_value_126, f.average_traded_value_60,
          f.absent_observation_days_60, f.zero_volume_days_60,
          f.liquidity_rank_126, f.liquidity_percentile_126,
          f.liquidity_percentile_126 AS liquidity_percentile,
          f.liquidity_bucket_126,
          adj.adjustment_quality AS price_adjustment_quality,
          adj.total_return_quality,
          CASE WHEN adj.adjustment_quality IN ('NO_ADJUSTMENT_REQUIRED', 'PRICE_ACTION_ADJUSTED_VERIFIED') THEN TRUE ELSE FALSE END AS price_adjustment_ok,
          CASE
            WHEN m.identity_quality IN ('OFFICIAL_EXCHANGE_IDENTITY', 'MULTI_SOURCE_VERIFIED', 'RECONSTRUCTED_HIGH_CONFIDENCE', 'RECONSTRUCTED_TRADING_IDENTITY')
              THEN m.identity_quality
            WHEN m.identity_quality IN ('PARTIAL', 'SINGLE_OFFICIAL_SOURCE') AND i.episode_count = 1 AND i.series_count = 1 AND i.isin_count <= 1
              THEN 'RECONSTRUCTED_TRADING_IDENTITY'
            ELSE m.identity_quality
          END AS research_identity_quality,
          CASE
            WHEN m.identity_quality IN ('OFFICIAL_EXCHANGE_IDENTITY', 'MULTI_SOURCE_VERIFIED', 'RECONSTRUCTED_HIGH_CONFIDENCE', 'RECONSTRUCTED_TRADING_IDENTITY') THEN TRUE
            WHEN m.identity_quality IN ('PARTIAL', 'SINGLE_OFFICIAL_SOURCE') AND i.episode_count = 1 AND i.series_count = 1 AND i.isin_count <= 1 THEN TRUE
            ELSE FALSE
          END AS research_identity_ok,
          CASE
            WHEN a.instrument_type = 'ORDINARY_EQUITY' THEN 'OFFICIAL_REFERENCE'
            ELSE 'EXPLICIT_EXCHANGE_MARKER'
          END AS instrument_type_quality,
          CASE WHEN COALESCE(s.trading_status, a.trading_status) = 'ACTIVE_TRADING'
            THEN COALESCE(s.status_quality, 'OBSERVED_TRADING_RECORD')
            ELSE COALESCE(s.status_quality, 'STATUS_EXCLUDED') END AS status_quality
        FROM read_parquet('{out}/active_universe_daily.parquet') a
        JOIN read_parquet('{out}/liquidity_features.parquet') f
          ON f.security_id = a.security_id AND CAST(f.date AS DATE) = CAST(a.date AS DATE)
        LEFT JOIN read_parquet('{out}/daily_prices_adjusted.parquet') adj
          ON adj.security_id = a.security_id AND CAST(adj.date AS DATE) = CAST(a.date AS DATE)
        LEFT JOIN read_parquet('{out}/security_master.parquet') m
          ON m.security_id = a.security_id
         AND m.listing_episode_id = a.listing_episode_id
         AND CAST(a.date AS DATE) >= CAST(m.effective_from AS DATE)
         AND (m.effective_to IS NULL OR CAST(a.date AS DATE) <= CAST(m.effective_to AS DATE))
        LEFT JOIN identity_checks i ON i.security_id = a.security_id
        LEFT JOIN read_parquet('{out}/trading_status_intervals.parquet') s
          ON s.security_id = a.security_id
         AND CAST(a.date AS DATE) >= CAST(s.status_start AS DATE)
         AND (s.status_end IS NULL OR CAST(a.date AS DATE) <= CAST(s.status_end AS DATE))
        WHERE CAST(a.date AS DATE) >= DATE '{start}' {end_clause}
          AND a.active
      ),
      ranked AS (
        SELECT b.*, me.month,
          ROW_NUMBER() OVER (PARTITION BY b.date ORDER BY b.median_traded_value_126 DESC NULLS LAST, b.security_id) AS rank_126,
          CASE WHEN b.instrument_type = '{instrument_type}'
             AND b.trading_status = '{trading_status}'
             AND b.research_identity_ok
             AND b.price >= {price_min}
             AND b.listing_age_sessions >= {listing_age_min}
             AND b.positive_volume_days_60 >= {positive_volume_min}
             AND b.median_traded_value_60 >= {median_value_min}
             AND b.price_adjustment_ok
            THEN TRUE ELSE FALSE END AS liquid_v1_eligible
        FROM base b
        JOIN month_end me ON me.date = b.date
        WHERE b.instrument_type = '{instrument_type}'
          AND b.trading_status = '{trading_status}'
      )
      SELECT r.*,
        r.median_traded_value_126 IS NOT NULL AND r.rank_126 <= 500 AS top500_liquidity,
        r.median_traded_value_126 IS NOT NULL AND r.rank_126 <= 750 AS top750_liquidity,
        r.median_traded_value_126 IS NOT NULL AND r.rank_126 <= 1000 AS top1000_liquidity,
        r.liquid_v1_eligible AS LIQUID_V1_eligible,
        r.liquid_v1_eligible AS NSE_BROAD_LIQUID_PIT_V1_eligible,
        'NSE_BROAD_LIQUID_PIT_V1' AS profile_id,
        'LIQUID_V1' AS profile_version,
        r.date AS as_of_date,
        CASE WHEN r.liquid_v1_eligible THEN 'ELIGIBLE' ELSE 'EXCLUDED' END AS eligibility_result,
        CASE
          WHEN r.liquid_v1_eligible THEN 'PASSED_LIQUID_V1'
          WHEN r.instrument_type <> '{instrument_type}' THEN 'FAILED_INSTRUMENT_TYPE'
          WHEN r.trading_status <> '{trading_status}' THEN 'FAILED_TRADING_STATUS'
          WHEN NOT r.research_identity_ok THEN 'FAILED_RESEARCH_IDENTITY'
          WHEN NOT r.price_adjustment_ok THEN 'FAILED_PRICE_ADJUSTMENT'
          WHEN r.price IS NULL OR r.price < {price_min} THEN 'FAILED_MIN_PRICE'
          WHEN r.listing_age_sessions IS NULL OR r.listing_age_sessions < {listing_age_min} THEN 'FAILED_MIN_HISTORY'
          WHEN r.positive_volume_days_60 IS NULL OR r.positive_volume_days_60 < {positive_volume_min} THEN 'FAILED_POSITIVE_VOLUME_DAYS_60'
          WHEN r.median_traded_value_60 IS NULL OR r.median_traded_value_60 < {median_value_min} THEN 'FAILED_MEDIAN_TRADED_VALUE_60'
          ELSE 'FAILED_UNKNOWN_PROFILE_RULE'
        END AS eligibility_reason_codes
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
                 MIN(date) FILTER (WHERE liquid_v1_eligible OR top750_liquidity) AS first_research_date,
                 MAX(date) FILTER (WHERE liquid_v1_eligible OR top750_liquidity) AS last_research_date,
                 MAX(CASE WHEN liquid_v1_eligible THEN 1 ELSE 0 END)::BOOLEAN AS enters_liquid_v1,
                 MAX(CASE WHEN top750_liquidity THEN 1 ELSE 0 END)::BOOLEAN AS enters_top750,
                 MIN(rank_126) FILTER (WHERE (liquid_v1_eligible OR top750_liquidity) AND rank_126 IS NOT NULL) AS best_rank_126,
                 MAX(rank_126) FILTER (WHERE (liquid_v1_eligible OR top750_liquidity) AND rank_126 IS NOT NULL) AS worst_rank_126,
                 MAX(median_traded_value_60) FILTER (WHERE liquid_v1_eligible OR top750_liquidity) AS max_median_traded_value_60,
                 MAX(median_traded_value_126) FILTER (WHERE liquid_v1_eligible OR top750_liquidity) AS max_median_traded_value_126,
                 MAX(positive_volume_days_60) FILTER (WHERE liquid_v1_eligible OR top750_liquidity) AS max_positive_volume_days_60,
                 MIN(research_identity_quality) FILTER (WHERE liquid_v1_eligible OR top750_liquidity) AS research_identity_quality,
                 MIN(price_adjustment_quality) FILTER (WHERE liquid_v1_eligible OR top750_liquidity) AS price_adjustment_quality,
                 MIN(CASE
                   WHEN (liquid_v1_eligible OR top750_liquidity) AND price_adjustment_ok THEN 1
                   WHEN (liquid_v1_eligible OR top750_liquidity) THEN 0
                   ELSE NULL
                 END)::BOOLEAN AS price_adjustment_ok,
                 MIN(instrument_type) FILTER (WHERE liquid_v1_eligible OR top750_liquidity) AS instrument_type,
                 MIN(instrument_type_quality) FILTER (WHERE liquid_v1_eligible OR top750_liquidity) AS instrument_type_quality,
                 MIN(status_quality) FILTER (WHERE liquid_v1_eligible OR top750_liquidity) AS status_quality,
                 MIN(CASE
                   WHEN (liquid_v1_eligible OR top750_liquidity) AND trading_status = 'ACTIVE_TRADING' THEN 1
                   WHEN (liquid_v1_eligible OR top750_liquidity) THEN 0
                   ELSE NULL
                 END)::BOOLEAN AS active_trading_ok
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
