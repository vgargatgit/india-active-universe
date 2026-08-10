#!/usr/bin/env python3
"""Build data-derived monthly universe and annual liquidity reports."""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--out-dir", default="reports")
    args = parser.parse_args()
    release = Path(args.release)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    c = duckdb.connect()
    active = (release / "active_universe_daily.parquet").as_posix().replace("'", "''")
    features = (release / "liquidity_features.parquet").as_posix().replace("'", "''")
    joined = f"""
        WITH feature_rows AS (
            SELECT CAST(date AS DATE) AS date, security_id, history_sessions,
                   median_traded_value_60, median_traded_value_126
            FROM read_parquet('{features}')
            WHERE instrument_type = 'ORDINARY_EQUITY'
        ), active_rows AS (
            SELECT CAST(date AS DATE) AS date, security_id
            FROM read_parquet('{active}')
            WHERE instrument_type = 'ORDINARY_EQUITY' AND active
        ), joined AS (
            SELECT a.date, a.security_id, f.history_sessions,
                   f.median_traded_value_60, f.median_traded_value_126,
                   strftime(a.date, '%Y-%m') AS month,
                   strftime(a.date, '%Y') AS year
            FROM active_rows a LEFT JOIN feature_rows f USING (date, security_id)
        )
    """
    monthly = c.execute(joined + """
        , month_end AS (
            SELECT *, max(date) OVER (PARTITION BY month) AS final_session
            FROM joined
        ), ranked AS (
            SELECT *, row_number() OVER (PARTITION BY month ORDER BY median_traded_value_126 DESC NULLS LAST) AS liquidity_rank
            FROM month_end WHERE date = final_session
        )
        SELECT month, final_session, count(*) AS active_ordinary_equities,
               count(*) FILTER (WHERE history_sessions >= 272) AS history_eligible,
               count(*) FILTER (WHERE history_sessions >= 272 AND median_traded_value_60 >= 5000000) AS example_liquid_v1,
               max(median_traded_value_126) FILTER (WHERE liquidity_rank = 500) AS top500_cutoff
        FROM ranked GROUP BY month, final_session ORDER BY month
    """).fetchall()
    lines = [
        "# Universe history",
        "",
        "Monthly counts use the final official market-data session in each month. `LIQUID_V1` is an example consumer profile, not a canonical strategy universe.",
        "",
        "| Month | Session | Active ordinary | History >=272 | Example liquid | Top-500 cutoff |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    lines.extend(f"| {month} | {session} | {active:,} | {history:,} | {liquid:,} | {cutoff if cutoff is not None else 'NA'} |" for month, session, active, history, liquid, cutoff in monthly)
    (out / "universe_history.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    annual = c.execute(joined + """
        , year_end AS (
            SELECT *, max(date) OVER (PARTITION BY year) AS final_session
            FROM joined
        ), cross_section AS (
            SELECT * FROM year_end WHERE date = final_session AND median_traded_value_60 IS NOT NULL
        )
        SELECT year, final_session,
               quantile_cont(median_traded_value_60, 0.50),
               quantile_cont(median_traded_value_60, 0.90),
               quantile_cont(median_traded_value_60, 0.95),
               count(*) FILTER (WHERE median_traded_value_60 >= 1000000),
               count(*) FILTER (WHERE median_traded_value_60 >= 5000000),
               count(*) FILTER (WHERE median_traded_value_60 >= 10000000),
               count(*) FILTER (WHERE median_traded_value_60 >= 50000000),
               count(*) FILTER (WHERE median_traded_value_60 >= 100000000)
        FROM cross_section GROUP BY year, final_session ORDER BY year
    """).fetchall()
    lines = [
        "# Liquidity history",
        "",
        "Each row uses the final official market-data session in the year and ordinary-equity securities only. ADV thresholds are descriptive, not canonical eligibility rules.",
        "",
        "| Year | Session | Median 60d value | P90 | P95 | >=1M | >=5M | >=10M | >=50M | >=100M |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    lines.extend(f"| {year} | {session} | {median:,.0f} | {p90:,.0f} | {p95:,.0f} | {m1:,} | {m5:,} | {m10:,} | {m50:,} | {m100:,} |" for year, session, median, p90, p95, m1, m5, m10, m50, m100 in annual)
    (out / "liquidity_history.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"monthly_rows={len(monthly)} annual_rows={len(annual)}")


if __name__ == "__main__":
    main()
