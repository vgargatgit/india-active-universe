from __future__ import annotations

import argparse
from pathlib import Path

import duckdb


def sql_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build liquidity features on official NSE session windows.")
    parser.add_argument("--prices", required=True)
    parser.add_argument("--calendar", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    prices = sql_path(Path(args.prices))
    calendar = sql_path(Path(args.calendar))
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    destination = sql_path(output)
    connection = duckdb.connect()
    try:
        columns = {
            row[0].lower()
            for row in connection.execute(f"DESCRIBE SELECT * FROM read_parquet('{prices}')").fetchall()
        }
    finally:
        connection.close()
    series_filter = "WHERE COALESCE(CAST(p.series AS VARCHAR), 'EQ') = 'EQ'" if "series" in columns else ""
    query = f"""
    COPY (
      WITH sessions AS (
        SELECT CAST(date AS DATE) AS session_date,
               ROW_NUMBER() OVER (ORDER BY CAST(date AS DATE)) AS session_number
        FROM read_parquet('{calendar}')
      ),
      p AS (
        SELECT p.*, CAST(p.date AS DATE) AS price_date, s.session_number
        FROM read_parquet('{prices}') p
        JOIN sessions s ON CAST(p.date AS DATE) = s.session_date
        {series_filter}
      ),
      bounds AS (
        SELECT security_id, MIN(session_number) AS first_session,
               MAX(session_number) AS last_session
        FROM p
        GROUP BY security_id
      ),
      grid AS (
        SELECT b.security_id, s.session_date, s.session_number,
               p.raw_close, p.volume, p.traded_value,
               p.security_id IS NOT NULL AS observed,
               LAG(p.raw_close) OVER (
                 PARTITION BY b.security_id ORDER BY s.session_number
               ) AS previous_session_close
        FROM bounds b
        JOIN sessions s
          ON s.session_number BETWEEN b.first_session AND b.last_session
        LEFT JOIN p
          ON p.security_id = b.security_id
         AND p.session_number = s.session_number
      ),
      features AS (
        SELECT g.*,
          COUNT(*) OVER history_window AS history_sessions,
          COUNT(*) FILTER (WHERE observed) OVER history_window AS observed_history_sessions,
          COUNT(*) FILTER (WHERE observed AND traded_value IS NOT NULL) OVER w20 AS valid_trade_days_20,
          COUNT(*) FILTER (WHERE observed AND traded_value IS NOT NULL) OVER w60 AS valid_trade_days_60,
          COUNT(*) FILTER (WHERE observed AND traded_value IS NOT NULL) OVER w126 AS valid_trade_days_126,
          COUNT(*) FILTER (WHERE observed AND traded_value IS NOT NULL) OVER w252 AS valid_trade_days_252,
          COUNT(*) FILTER (WHERE observed AND volume > 0) OVER w20 AS positive_volume_days_20,
          COUNT(*) FILTER (WHERE observed AND volume > 0) OVER w60 AS positive_volume_days_60,
          COUNT(*) FILTER (WHERE observed AND volume > 0) OVER w126 AS positive_volume_days_126,
          COUNT(*) FILTER (WHERE observed AND volume > 0) OVER w252 AS positive_volume_days_252,
          COUNT(*) FILTER (WHERE observed AND COALESCE(volume, 0) <= 0) OVER w20 AS zero_volume_days_20,
          COUNT(*) FILTER (WHERE observed AND COALESCE(volume, 0) <= 0) OVER w60 AS zero_volume_days_60,
          COUNT(*) FILTER (WHERE observed AND COALESCE(volume, 0) <= 0) OVER w126 AS zero_volume_days_126,
          COUNT(*) FILTER (WHERE observed AND COALESCE(volume, 0) <= 0) OVER w252 AS zero_volume_days_252,
          COUNT(*) FILTER (WHERE NOT observed) OVER w20 AS absent_observation_days_20,
          COUNT(*) FILTER (WHERE NOT observed) OVER w60 AS absent_observation_days_60,
          COUNT(*) FILTER (WHERE NOT observed) OVER w126 AS absent_observation_days_126,
          COUNT(*) FILTER (WHERE NOT observed) OVER w252 AS absent_observation_days_252,
          QUANTILE_CONT(traded_value, 0.5) FILTER (WHERE observed) OVER w20 AS median_traded_value_20,
          QUANTILE_CONT(traded_value, 0.5) FILTER (WHERE observed) OVER w60 AS median_traded_value_60,
          QUANTILE_CONT(traded_value, 0.5) FILTER (WHERE observed) OVER w126 AS median_traded_value_126,
          QUANTILE_CONT(traded_value, 0.5) FILTER (WHERE observed) OVER w252 AS median_traded_value_252,
          AVG(traded_value) FILTER (WHERE observed) OVER w20 AS average_traded_value_20,
          AVG(traded_value) FILTER (WHERE observed) OVER w60 AS average_traded_value_60,
          AVG(traded_value) FILTER (WHERE observed) OVER w126 AS average_traded_value_126,
          AVG(traded_value) FILTER (WHERE observed) OVER w252 AS average_traded_value_252,
          COUNT(*) FILTER (WHERE observed AND raw_close IS NOT NULL AND previous_session_close IS NOT NULL AND raw_close = previous_session_close) OVER w60 AS stale_price_days_60
        FROM grid g
        WINDOW
          history_window AS (PARTITION BY security_id ORDER BY session_number ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),
          w20 AS (PARTITION BY security_id ORDER BY session_number ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
          w60 AS (PARTITION BY security_id ORDER BY session_number ROWS BETWEEN 59 PRECEDING AND CURRENT ROW),
          w126 AS (PARTITION BY security_id ORDER BY session_number ROWS BETWEEN 125 PRECEDING AND CURRENT ROW),
          w252 AS (PARTITION BY security_id ORDER BY session_number ROWS BETWEEN 251 PRECEDING AND CURRENT ROW)
      ),
      ranked AS (
        SELECT f.*,
          CUME_DIST() OVER (PARTITION BY session_date ORDER BY median_traded_value_126 NULLS LAST) AS liquidity_percentile_126,
          ROW_NUMBER() OVER (PARTITION BY session_date ORDER BY median_traded_value_126 DESC NULLS LAST, security_id) AS liquidity_rank_126
        FROM features f
        WHERE observed
      )
      SELECT p.* EXCLUDE (price_date, session_number),
        r.history_sessions,
        r.observed_history_sessions,
        r.history_sessions AS listing_age_sessions,
        DATE_DIFF('day', MIN(r.session_date) OVER (PARTITION BY r.security_id), r.session_date) AS listing_age_calendar_days,
        p.raw_close AS price,
        'ACTIVE_TRADING' AS listing_status,
        r.valid_trade_days_20, r.valid_trade_days_60, r.valid_trade_days_126, r.valid_trade_days_252,
        r.positive_volume_days_20, r.positive_volume_days_60, r.positive_volume_days_126, r.positive_volume_days_252,
        r.zero_volume_days_20, r.zero_volume_days_60, r.zero_volume_days_126, r.zero_volume_days_252,
        r.absent_observation_days_20, r.absent_observation_days_60, r.absent_observation_days_126, r.absent_observation_days_252,
        r.median_traded_value_20, r.median_traded_value_60, r.median_traded_value_126, r.median_traded_value_252,
        r.average_traded_value_20, r.average_traded_value_60, r.average_traded_value_126, r.average_traded_value_252,
        r.stale_price_days_60,
        r.liquidity_percentile_126,
        CASE WHEN r.liquidity_percentile_126 > 0.8 THEN 'LIQUIDITY_Q1'
             WHEN r.liquidity_percentile_126 > 0.6 THEN 'LIQUIDITY_Q2'
             WHEN r.liquidity_percentile_126 > 0.4 THEN 'LIQUIDITY_Q3'
             WHEN r.liquidity_percentile_126 > 0.2 THEN 'LIQUIDITY_Q4'
             ELSE 'LIQUIDITY_Q5' END AS liquidity_bucket_126,
        r.liquidity_rank_126,
        r.session_date AS feature_as_of_date,
        'OFFICIAL_NSE_SESSION_WINDOW' AS liquidity_window_definition
      FROM ranked r
      JOIN p ON p.security_id = r.security_id AND p.session_number = r.session_number
    ) TO '{destination}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 25000)
    """
    connection = duckdb.connect()
    try:
        connection.execute("PRAGMA threads=4")
        connection.execute(query)
        count = connection.execute(f"SELECT COUNT(*) FROM read_parquet('{destination}')").fetchone()[0]
    finally:
        connection.close()
    print(f"features={count}")


if __name__ == "__main__":
    main()
