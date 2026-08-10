from __future__ import annotations

import argparse
from pathlib import Path

import duckdb


def sql_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prices", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    prices = sql_path(Path(args.prices))
    output = sql_path(Path(args.out))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    query = f"""
    COPY (
      WITH ordered AS (
        SELECT p.*, ROW_NUMBER() OVER (PARTITION BY security_id ORDER BY date) AS history_sessions,
          MIN(date) OVER (PARTITION BY security_id) AS first_observed_date,
          LAG(raw_close) OVER (PARTITION BY security_id ORDER BY date) AS previous_close
        FROM read_parquet('{prices}') p
      ),
      feature_base AS (
        SELECT o.* EXCLUDE (history_sessions, first_observed_date, previous_close),
          history_sessions,
          history_sessions AS listing_age_sessions,
          DATE_DIFF('day', CAST(first_observed_date AS DATE), CAST(date AS DATE)) AS listing_age_calendar_days,
          raw_close AS price,
          'ACTIVE_TRADING' AS listing_status,
          COUNT(traded_value) OVER w20 AS valid_trade_days_20,
          COUNT(traded_value) OVER w60 AS valid_trade_days_60,
          COUNT(traded_value) OVER w126 AS valid_trade_days_126,
          COUNT(traded_value) OVER w252 AS valid_trade_days_252,
          COUNT(*) FILTER (WHERE COALESCE(volume, 0) <= 0) OVER w20 AS zero_volume_days_20,
          COUNT(*) FILTER (WHERE COALESCE(volume, 0) <= 0) OVER w60 AS zero_volume_days_60,
          COUNT(*) FILTER (WHERE COALESCE(volume, 0) <= 0) OVER w126 AS zero_volume_days_126,
          COUNT(*) FILTER (WHERE COALESCE(volume, 0) <= 0) OVER w252 AS zero_volume_days_252,
          QUANTILE_CONT(traded_value, 0.5) OVER w20 AS median_traded_value_20,
          QUANTILE_CONT(traded_value, 0.5) OVER w60 AS median_traded_value_60,
          QUANTILE_CONT(traded_value, 0.5) OVER w126 AS median_traded_value_126,
          QUANTILE_CONT(traded_value, 0.5) OVER w252 AS median_traded_value_252,
          AVG(traded_value) OVER w20 AS average_traded_value_20,
          AVG(traded_value) OVER w60 AS average_traded_value_60,
          AVG(traded_value) OVER w126 AS average_traded_value_126,
          AVG(traded_value) OVER w252 AS average_traded_value_252,
          COUNT(*) FILTER (WHERE raw_close IS NOT NULL AND previous_close IS NOT NULL AND raw_close = previous_close) OVER w60 AS stale_price_days_60,
          date AS feature_as_of_date
        FROM ordered o
        WINDOW
          w20 AS (PARTITION BY security_id ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
          w60 AS (PARTITION BY security_id ORDER BY date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW),
          w126 AS (PARTITION BY security_id ORDER BY date ROWS BETWEEN 125 PRECEDING AND CURRENT ROW),
          w252 AS (PARTITION BY security_id ORDER BY date ROWS BETWEEN 251 PRECEDING AND CURRENT ROW)
      ),
      ranked AS (
        SELECT f.*, CUME_DIST() OVER (PARTITION BY date ORDER BY median_traded_value_60) AS liquidity_percentile_60
        FROM feature_base f
      )
      SELECT r.*,
        CASE WHEN liquidity_percentile_60 > 0.8 THEN 'LIQUIDITY_Q1'
             WHEN liquidity_percentile_60 > 0.6 THEN 'LIQUIDITY_Q2'
             WHEN liquidity_percentile_60 > 0.4 THEN 'LIQUIDITY_Q3'
             WHEN liquidity_percentile_60 > 0.2 THEN 'LIQUIDITY_Q4'
             ELSE 'LIQUIDITY_Q5' END AS liquidity_bucket_60
      FROM ranked r
    ) TO '{output}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 25000)
    """
    connection = duckdb.connect()
    try:
        connection.execute("PRAGMA threads=4")
        connection.execute(query)
        count = connection.execute(f"SELECT COUNT(*) FROM read_parquet('{output}')").fetchone()[0]
    finally:
        connection.close()
    print(f"features={count}")


if __name__ == "__main__":
    main()
