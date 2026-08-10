#!/usr/bin/env python3
"""Materialize effective-dated company-name and ISIN history tables."""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--master", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    master = str(args.master).replace("'", "''")
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    name_out = (out / "company_name_history.parquet").as_posix().replace("'", "''")
    isin_out = (out / "isin_history.parquet").as_posix().replace("'", "''")
    c = duckdb.connect()
    c.execute(
        f"""COPY (
            SELECT DISTINCT issuer_id, company_name, effective_from, effective_to,
                   identity_quality, coalesce(identity_source, 'NSE_HISTORICAL_OBSERVATION') AS source
            FROM read_parquet('{master}')
            WHERE issuer_id IS NOT NULL AND company_name IS NOT NULL
            ORDER BY issuer_id, effective_from, effective_to
        ) TO '{name_out}' (FORMAT PARQUET, COMPRESSION ZSTD)"""
    )
    c.execute(
        f"""COPY (
            SELECT DISTINCT security_id, isin, effective_from, effective_to,
                   'OBSERVED_ISIN' AS event_type,
                   coalesce(identity_source, 'NSE_HISTORICAL_OBSERVATION') AS source,
                   identity_quality
            FROM read_parquet('{master}')
            WHERE security_id IS NOT NULL AND isin IS NOT NULL
            ORDER BY security_id, effective_from, effective_to
        ) TO '{isin_out}' (FORMAT PARQUET, COMPRESSION ZSTD)"""
    )
    print(f"company_name_history={name_out} isin_history={isin_out}")


if __name__ == "__main__":
    main()
