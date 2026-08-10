#!/usr/bin/env python3
"""Prioritize unresolved identities using observed liquidity, not fuzzy matching."""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    root = Path(args.release)
    master = (root / "security_master.parquet").as_posix().replace("'", "''")
    features = (root / "liquidity_features.parquet").as_posix().replace("'", "''")
    c = duckdb.connect()
    rows = c.execute(
        f"""
        WITH identities AS (
            SELECT security_id, any_value(symbol) AS symbol, any_value(company_name) AS company_name,
                   any_value(candidate_isin) AS candidate_isin,
                   min(first_seen) AS first_seen, max(last_seen) AS last_seen,
                   any_value(identity_quality) AS identity_quality
            FROM read_parquet('{master}')
            GROUP BY security_id
            HAVING bool_and(identity_quality <> 'SINGLE_OFFICIAL_SOURCE')
        ), liquidity AS (
            SELECT security_id, max(median_traded_value_126) AS max_median_traded_value_126,
                   max(median_traded_value_60) AS max_median_traded_value_60,
                   count(*) FILTER (WHERE instrument_type = 'ORDINARY_EQUITY') AS feature_rows
            FROM read_parquet('{features}')
            GROUP BY security_id
        )
        SELECT i.*, l.max_median_traded_value_126, l.max_median_traded_value_60, coalesce(l.feature_rows, 0) AS feature_rows,
               CASE WHEN coalesce(l.max_median_traded_value_126, 0) >= 5000000 THEN 'HIGH'
                    WHEN coalesce(l.max_median_traded_value_126, 0) >= 1000000 THEN 'MEDIUM'
                    ELSE 'LOW' END AS downstream_priority
        FROM identities i LEFT JOIN liquidity l USING (security_id)
        ORDER BY CASE downstream_priority WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,
                 max_median_traded_value_126 DESC NULLS LAST, security_id
        """
    ).fetchall()
    headers = ["security_id", "symbol", "company_name", "candidate_isin", "first_seen", "last_seen", "identity_quality", "max_median_traded_value_126", "max_median_traded_value_60", "feature_rows", "downstream_priority"]
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Identity resolution queue", "", "Rows remain non-canonical until approved evidence or a validated manual override is supplied.", "", f"Unresolved security IDs: {len(rows):,}", "", "| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        cells = ["" if value is None else str(value).replace("|", "/") for value in row]
        lines.append("| " + " | ".join(cells) + " |")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"unresolved_security_ids={len(rows)}")


if __name__ == "__main__":
    main()
