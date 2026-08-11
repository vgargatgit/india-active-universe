#!/usr/bin/env python3
"""Diagnose identity continuity failures around the 2011 NSE ISIN transition."""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb


WATCH_SYMBOLS = [
    "HDFCBANK",
    "BHEL",
    "TATAPOWER",
    "TATAMOTORS",
    "RALLIS",
    "GSFC",
    "GRAVITA",
    "WABAG",
    "CRISIL",
    "VIPIND",
]


def sql_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def rows_to_table(headers: list[str], rows: list[tuple]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        out.append("| " + " | ".join("" if value is None else f"`{value}`" for value in row) + " |")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", default="releases/india_equity_data_v2.1.1")
    parser.add_argument("--reports", default="reports")
    parser.add_argument("--start", default="2011-04-01")
    parser.add_argument("--end", default="2012-08-31")
    args = parser.parse_args()

    release = Path(args.release)
    reports = Path(args.reports)
    monthly = sql_path(release / "research_universe_monthly.parquet")
    raw = sql_path(release / "daily_prices_raw.parquet")
    calendar = sql_path(release / "trading_calendar.parquet")

    con = duckdb.connect()
    con.execute(f"""
      CREATE TEMP VIEW monthly AS
      SELECT * FROM read_parquet('{monthly}')
      WHERE CAST(date AS DATE) BETWEEN DATE '{args.start}' AND DATE '{args.end}';
    """)
    con.execute(f"""
      CREATE TEMP VIEW raw AS
      SELECT *, CAST(date AS DATE) AS d FROM read_parquet('{raw}')
      WHERE CAST(date AS DATE) BETWEEN DATE '{args.start}' AND DATE '{args.end}'
        AND series = 'EQ'
        AND instrument_type = 'ORDINARY_EQUITY';
    """)
    con.execute(f"""
      CREATE TEMP VIEW cal AS
      SELECT CAST(date AS DATE) AS d, session_index
      FROM read_parquet('{calendar}');
    """)

    monthly_rows = con.execute("""
      WITH base AS (
        SELECT
          m.date,
          COUNT(*) FILTER (WHERE active AND instrument_type = 'ORDINARY_EQUITY') AS active_ordinary_security_ids,
          COUNT(DISTINCT symbol_at_date) AS unique_symbols,
          COUNT(DISTINCT isin) AS unique_isins,
          COUNT(*) FILTER (WHERE NSE_BROAD_LIQUID_PIT_V1_eligible) AS liquid_v1,
          COUNT(*) FILTER (WHERE top750_liquidity) AS top750,
          MIN(history_sessions) AS min_history_sessions,
          MAX(history_sessions) AS max_history_sessions,
          ROUND(AVG(history_sessions), 2) AS avg_history_sessions,
          COUNT(*) FILTER (WHERE history_sessions <= 60) AS history_sessions_le_60,
          COUNT(*) FILTER (WHERE NOT NSE_BROAD_LIQUID_PIT_V1_eligible AND eligibility_reason_codes LIKE '%FAILED_MIN_HISTORY%') AS failed_min_history,
          COUNT(*) FILTER (WHERE NOT NSE_BROAD_LIQUID_PIT_V1_eligible AND eligibility_reason_codes LIKE '%FAILED_MIN_PRICE%') AS failed_min_price,
          COUNT(*) FILTER (WHERE NOT NSE_BROAD_LIQUID_PIT_V1_eligible AND eligibility_reason_codes LIKE '%FAILED_POSITIVE_VOLUME_DAYS_60%') AS failed_positive_volume_60,
          COUNT(*) FILTER (WHERE NOT NSE_BROAD_LIQUID_PIT_V1_eligible AND eligibility_reason_codes LIKE '%FAILED_MEDIAN_TRADED_VALUE_60%') AS failed_median_traded_value_60,
          COUNT(*) FILTER (WHERE NOT research_identity_ok) AS failed_identity_gate,
          COUNT(*) FILTER (WHERE instrument_type <> 'ORDINARY_EQUITY') AS failed_instrument_gate,
          COUNT(*) FILTER (WHERE trading_status <> 'ACTIVE_TRADING') AS failed_status_gate
        FROM monthly m
        GROUP BY 1
      ), dup_symbol AS (
        SELECT date, COUNT(*) AS symbols_with_multiple_security_ids
        FROM (
          SELECT date, symbol_at_date
          FROM monthly
          GROUP BY 1, 2
          HAVING COUNT(DISTINCT security_id) > 1
        )
        GROUP BY 1
      ), changed_60 AS (
        SELECT m.date, COUNT(DISTINCT w.symbol_at_date) AS symbols_changed_security_id_prev_60_sessions
        FROM (SELECT DISTINCT date FROM monthly) m
        JOIN cal cm ON cm.d = m.date
        JOIN cal cw ON cw.session_index BETWEEN cm.session_index - 60 AND cm.session_index
        JOIN raw w ON w.d = cw.d
        GROUP BY 1
        HAVING COUNT(DISTINCT w.security_id) > 0
      ), changed_60_symbols AS (
        SELECT date, COUNT(*) AS symbols_changed_security_id_prev_60_sessions
        FROM (
          SELECT m.date, w.symbol_at_date
          FROM (SELECT DISTINCT date FROM monthly) m
          JOIN cal cm ON cm.d = m.date
          JOIN cal cw ON cw.session_index BETWEEN cm.session_index - 60 AND cm.session_index
          JOIN raw w ON w.d = cw.d
          GROUP BY 1, 2
          HAVING COUNT(DISTINCT w.security_id) > 1
        )
        GROUP BY 1
      )
      SELECT
        base.date,
        active_ordinary_security_ids,
        unique_symbols,
        unique_isins,
        COALESCE(symbols_with_multiple_security_ids, 0),
        COALESCE(symbols_changed_security_id_prev_60_sessions, 0),
        history_sessions_le_60,
        liquid_v1,
        top750,
        min_history_sessions,
        max_history_sessions,
        avg_history_sessions,
        failed_min_history,
        failed_min_price,
        failed_positive_volume_60,
        failed_median_traded_value_60,
        failed_status_gate,
        failed_identity_gate,
        failed_instrument_gate
      FROM base
      LEFT JOIN dup_symbol USING (date)
      LEFT JOIN changed_60_symbols USING (date)
      ORDER BY date;
    """).fetchall()

    zero_months = [row for row in monthly_rows if row[7] == 0]
    first_zero = zero_months[0][0] if zero_months else None
    prior = con.execute("""
      SELECT MAX(date) FROM monthly
      WHERE date < DATE '2011-06-30' AND NSE_BROAD_LIQUID_PIT_V1_eligible
    """).fetchone()[0]

    example_rows = con.execute(f"""
      SELECT
        symbol_at_date,
        security_id,
        MIN(d) AS first_date,
        MAX(d) AS last_date,
        COUNT(*) AS observations,
        MIN(isin) AS min_isin,
        MAX(isin) AS max_isin,
        MIN(raw_close) AS min_close,
        MAX(raw_close) AS max_close
      FROM raw
      WHERE symbol_at_date IN ({",".join("'" + item + "'" for item in WATCH_SYMBOLS)})
      GROUP BY 1, 2
      ORDER BY symbol_at_date, first_date;
    """).fetchall()

    report = [
        "# Identity transition root cause",
        "",
        f"Release inspected: `{release}`.",
        f"Window: `{args.start}` through `{args.end}`.",
        "",
        "## Finding",
        "",
        "The June-2011 `LIQUID_V1` collapse is caused by artificial security-history resets, not by market behavior.",
        f"The first zero-sized `LIQUID_V1` monthly snapshot is `{first_zero}`.",
        "On `2011-06-30`, every non-eligible row fails either `FAILED_MIN_HISTORY` or `FAILED_MIN_PRICE`; there are no identity, instrument, or status gate failures in the monthly artifact.",
        "The failure is therefore upstream: canonical security IDs changed when ISINs appeared in the source, so continuous securities were treated as new histories.",
        "",
        "## Monthly diagnostics",
        "",
    ]
    report.extend(rows_to_table([
        "date",
        "active ordinary IDs",
        "symbols",
        "ISINs",
        "symbols with >1 ID same month",
        "symbols changed ID prev 60 sessions",
        "history <=60",
        "LIQUID_V1",
        "Top750",
        "min hist",
        "max hist",
        "avg hist",
        "fail history",
        "fail price",
        "fail volume60",
        "fail median60",
        "fail status",
        "fail identity",
        "fail instrument",
    ], monthly_rows))
    report.extend([
        "",
        "## Required example securities",
        "",
    ])
    report.extend(rows_to_table([
        "symbol",
        "security_id",
        "first date",
        "last date",
        "obs",
        "min ISIN",
        "max ISIN",
        "min close",
        "max close",
    ], example_rows))
    report.extend([
        "",
        "## Conclusion",
        "",
        "This release must not promote an interval spanning June 2011.",
        "The identity gate is insufficient because each generated security ID is internally unambiguous while the continuous economic security is fragmented across IDs.",
    ])
    write(reports / "identity_transition_root_cause.md", "\n".join(report))

    transition_rows = con.execute("""
      WITH ordered AS (
        SELECT
          symbol_at_date AS symbol,
          series,
          security_id,
          MIN(d) AS first_date,
          MAX(d) AS last_date,
          COUNT(*) AS observations,
          MIN(isin) AS min_isin,
          MAX(isin) AS max_isin,
          ANY_VALUE(company_name) AS company_name
        FROM raw
        GROUP BY 1, 2, 3
      ), pairs AS (
        SELECT
          a.symbol,
          a.series,
          a.security_id AS pre_security_id,
          b.security_id AS post_security_id,
          a.max_isin AS pre_isin,
          b.min_isin AS post_isin,
          a.last_date AS last_pre_date,
          b.first_date AS first_post_date,
          a.company_name AS pre_company_name,
          b.company_name AS post_company_name
        FROM ordered a
        JOIN ordered b
          ON a.symbol = b.symbol
         AND a.series = b.series
         AND a.security_id <> b.security_id
         AND a.last_date < b.first_date
        WHERE NOT EXISTS (
          SELECT 1
          FROM ordered x
          WHERE x.symbol = a.symbol
            AND x.series = a.series
            AND x.first_date > a.last_date
            AND x.first_date < b.first_date
        )
      ), enriched AS (
        SELECT
          p.*,
          cp.session_index - ca.session_index AS official_session_gap,
          rp.raw_close AS last_pre_close,
          rn.raw_close AS first_post_close,
          ROUND(rn.raw_close / NULLIF(rp.raw_close, 0), 6) AS close_ratio,
          CASE
            WHEN p.pre_isin IS NULL AND p.post_isin IS NOT NULL AND cp.session_index - ca.session_index <= 1 THEN 'LIKELY_SAME_SECURITY_REVIEW'
            WHEN p.pre_isin IS NOT NULL AND p.post_isin IS NOT NULL AND cp.session_index - ca.session_index <= 1 THEN 'LIKELY_SAME_SECURITY_REVIEW'
            WHEN cp.session_index - ca.session_index <= 5 THEN 'AMBIGUOUS'
            ELSE 'AMBIGUOUS'
          END AS candidate_conclusion
        FROM pairs p
        JOIN cal ca ON ca.d = p.last_pre_date
        JOIN cal cp ON cp.d = p.first_post_date
        JOIN raw rp ON rp.symbol_at_date = p.symbol AND rp.series = p.series AND rp.security_id = p.pre_security_id AND rp.d = p.last_pre_date
        JOIN raw rn ON rn.symbol_at_date = p.symbol AND rn.series = p.series AND rn.security_id = p.post_security_id AND rn.d = p.first_post_date
      )
      SELECT
        symbol,
        pre_security_id,
        post_security_id,
        pre_isin,
        post_isin,
        last_pre_date,
        first_post_date,
        official_session_gap,
        pre_company_name,
        post_company_name,
        last_pre_close,
        first_post_close,
        close_ratio,
        series,
        candidate_conclusion
      FROM enriched
      ORDER BY
        CASE WHEN symbol IN ('HDFCBANK','BHEL','TATAPOWER','TATAMOTORS','RALLIS','GSFC','GRAVITA','WABAG','CRISIL','VIPIND') THEN 0 ELSE 1 END,
        symbol,
        first_post_date;
    """).fetchall()

    conclusion_counts = con.execute("""
      WITH transitions AS (
        SELECT symbol_at_date AS symbol, security_id, MIN(d) AS first_date, MAX(d) AS last_date
        FROM raw
        GROUP BY 1, 2
      ), pairs AS (
        SELECT a.symbol, a.security_id pre_id, b.security_id post_id
        FROM transitions a
        JOIN transitions b ON a.symbol = b.symbol AND a.security_id <> b.security_id AND a.last_date < b.first_date
        WHERE NOT EXISTS (
          SELECT 1 FROM transitions x
          WHERE x.symbol = a.symbol AND x.first_date > a.last_date AND x.first_date < b.first_date
        )
      )
      SELECT COUNT(DISTINCT symbol), COUNT(*) FROM pairs;
    """).fetchone()

    transition_report = [
        "# Pre/post ISIN identity transition audit",
        "",
        f"Release inspected: `{release}`.",
        f"Window: `{args.start}` through `{args.end}`.",
        "",
        f"Symbols with adjacent security-ID transitions: `{conclusion_counts[0]}`.",
        f"Adjacent transition pairs: `{conclusion_counts[1]}`.",
        "",
        "Candidate conclusions are diagnostic only. They do not merge identities.",
        "",
    ]
    transition_report.extend(rows_to_table([
        "symbol",
        "pre security_id",
        "post security_id",
        "pre ISIN",
        "post ISIN",
        "last pre date",
        "first post date",
        "gap sessions",
        "pre company",
        "post company",
        "last pre close",
        "first post close",
        "close ratio",
        "series",
        "candidate conclusion",
    ], transition_rows[:300]))
    if len(transition_rows) > 300:
        transition_report.extend(["", f"Report truncated to first `300` of `{len(transition_rows)}` adjacent transition pairs."])
    transition_report.extend([
        "",
        "## Known-example answer",
        "",
        "The required examples show multiple generated security IDs during continuous same-symbol NSE EQ trading.",
        "The first transition for each is from a no-ISIN source identity to an ISIN-backed source identity on or near `2011-06-22`.",
        "Several then transition again when a split/face-value event changes the ISIN.",
        "These are not proven symbol-reuse cases from this evidence; they are continuity candidates that require canonical identity repair with effective-dated ISIN history.",
    ])
    write(reports / "pre_post_isin_identity_transition.md", "\n".join(transition_report))

    spike_rows = con.execute("""
      WITH yearly AS (
        SELECT
          EXTRACT(year FROM d) AS year,
          COUNT(DISTINCT security_id) AS active_ordinary_security_ids,
          COUNT(DISTINCT symbol_at_date) AS unique_symbols,
          COUNT(DISTINCT isin) AS unique_isins,
          COUNT(DISTINCT security_id) FILTER (WHERE isin IS NULL) AS no_isin_security_ids,
          COUNT(DISTINCT security_id) FILTER (WHERE isin IS NOT NULL) AS isin_security_ids
        FROM raw
        GROUP BY 1
      ), fragmented AS (
        SELECT
          year,
          COUNT(*) AS fragmented_symbols
        FROM (
          SELECT EXTRACT(year FROM d) AS year, symbol_at_date
          FROM raw
          GROUP BY 1, 2
          HAVING COUNT(DISTINCT security_id) > 1
        )
        GROUP BY 1
      )
      SELECT
        y.year,
        active_ordinary_security_ids,
        unique_symbols,
        unique_isins,
        no_isin_security_ids,
        isin_security_ids,
        active_ordinary_security_ids - unique_symbols AS security_id_minus_symbol_count,
        COALESCE(fragmented_symbols, 0) AS fragmented_symbols
      FROM yearly y
      LEFT JOIN fragmented f USING (year)
      ORDER BY y.year;
    """).fetchall()
    spike_report = [
        "# 2011 identity count spike audit",
        "",
        f"Release inspected: `{release}`.",
        f"Window: `{args.start}` through `{args.end}`.",
        "",
        "## Finding",
        "",
        "The active-ordinary count spike is explained by duplicated generated security IDs, not by a doubled investable market.",
        "In 2011, the same symbol population is split between no-ISIN and ISIN-backed security IDs.",
        "",
    ]
    spike_report.extend(rows_to_table([
        "year",
        "active ordinary security IDs",
        "unique symbols",
        "unique ISINs",
        "no-ISIN security IDs",
        "ISIN security IDs",
        "ID minus symbol count",
        "fragmented symbols",
    ], spike_rows))
    spike_report.extend([
        "",
        "## Release blocker",
        "",
        "The count spike must become a hard promotion blocker until canonical continuity removes source-format fragmentation or explicitly classifies true security changes.",
    ])
    write(reports / "2011_identity_count_spike_audit.md", "\n".join(spike_report))

    print({"root_cause_report": str(reports / "identity_transition_root_cause.md"), "transition_report": str(reports / "pre_post_isin_identity_transition.md"), "spike_report": str(reports / "2011_identity_count_spike_audit.md"), "transition_pairs": len(transition_rows)})


if __name__ == "__main__":
    main()
