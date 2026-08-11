#!/usr/bin/env python3
"""Build a trading calendar only from dated official market observations."""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prices", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    prices = str(args.prices).replace("'", "''")
    destination = str(output).replace("'", "''")
    con.execute(
        f"""COPY (
            SELECT date,
                   (ROW_NUMBER() OVER (ORDER BY CAST(date AS DATE)) - 1)::BIGINT AS session_index,
                   'OFFICIAL_NSE_MARKET_DATA' AS session_evidence,
                   count(DISTINCT source_file_id)::BIGINT AS source_file_count,
                   array_agg(DISTINCT source_file_id ORDER BY source_file_id) AS source_file_ids,
                   array_agg(DISTINCT source_sha256 ORDER BY source_sha256) AS source_sha256s,
                   count(DISTINCT security_id)::BIGINT AS observed_security_count,
                   count(*) FILTER (WHERE instrument_type = 'ORDINARY_EQUITY')::BIGINT AS ordinary_equity_observation_count,
                   count(*) FILTER (WHERE instrument_type <> 'ORDINARY_EQUITY')::BIGINT AS non_ordinary_observation_count,
                   count(*)::BIGINT AS observation_count
            FROM read_parquet('{prices}')
            GROUP BY date
            ORDER BY date
        ) TO '{destination}' (FORMAT PARQUET, COMPRESSION ZSTD)""",
    )
    print(f"calendar={output}")


if __name__ == "__main__":
    main()
