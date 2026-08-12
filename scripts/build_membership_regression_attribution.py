#!/usr/bin/env python3
"""Build row-level economic membership and signal-price regression attribution."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import duckdb

from india_active_universe.profiles import (
    CURRENT_PROVEN_RESEARCH_END_DATE,
    CURRENT_PROVEN_RESEARCH_START_DATE,
)

FLAGS = (
    ("LIQUID_V1", "NSE_BROAD_LIQUID_PIT_V1_eligible"),
    ("TOP500", "top500_liquidity"),
    ("TOP750", "top750_liquidity"),
    ("TOP1000", "top1000_liquidity"),
)
TOP_FLAGS = {"TOP500", "TOP750", "TOP1000"}
NON_ORDINARY_MARKERS = (
    "GOLD", "NIFTY", "ETF", "BEES", "HANGSENG", "LIQUID", "MOM", "NV20", "PSUBNK", "BANKETF",
)


def sql(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _column_expr(alias: str, column: str, default: str) -> str:
    return f"{alias}.{column}" if default == "RAW" else f"COALESCE({alias}.{column}, {default})"


def build_differences(
    baseline: Path,
    candidate: Path,
    out: Path,
    signal_out: Path,
    *,
    start: str = CURRENT_PROVEN_RESEARCH_START_DATE,
    end: str = CURRENT_PROVEN_RESEARCH_END_DATE,
) -> dict[str, Any]:
    b = sql(baseline)
    c = sql(candidate)
    o = sql(out)
    so = sql(signal_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    signal_out.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    try:
        con.execute(f"""
          CREATE OR REPLACE TEMP VIEW base_monthly AS
          SELECT CAST(date AS DATE) AS date,
            UPPER(symbol_at_date) AS symbol_at_date,
            any_value(security_id) AS security_id,
            any_value(isin) AS isin,
            any_value(instrument_type) AS instrument_type,
            any_value(trading_status) AS trading_status,
            max(COALESCE(history_sessions, 0)) AS history_sessions,
            max(COALESCE(listing_age_sessions, 0)) AS listing_age_sessions,
            max(COALESCE(positive_volume_days_60, 0)) AS positive_volume_days_60,
            max(COALESCE(median_traded_value_60, 0)) AS median_traded_value_60,
            max(COALESCE(median_traded_value_126, 0)) AS median_traded_value_126,
            min(rank_126) AS rank_126,
            bool_or(COALESCE(NSE_BROAD_LIQUID_PIT_V1_eligible, false)) AS liquid_v1,
            bool_or(COALESCE(top500_liquidity, false)) AS top500,
            bool_or(COALESCE(top750_liquidity, false)) AS top750,
            bool_or(COALESCE(top1000_liquidity, false)) AS top1000,
            any_value(research_identity_quality) AS research_identity_quality,
            bool_or(COALESCE(research_identity_ok, false)) AS research_identity_ok,
            bool_or(COALESCE(price_adjustment_ok, false)) AS price_adjustment_ok,
            any_value(eligibility_result) AS eligibility_result
          FROM read_parquet('{b}/research_universe_monthly.parquet')
          WHERE CAST(date AS DATE) BETWEEN DATE '{start}' AND DATE '{end}'
          GROUP BY 1, 2
        """)
        con.execute(f"""
          CREATE OR REPLACE TEMP VIEW cand_monthly AS
          SELECT CAST(date AS DATE) AS date,
            UPPER(symbol_at_date) AS symbol_at_date,
            any_value(security_id) AS security_id,
            any_value(isin) AS isin,
            any_value(instrument_type) AS instrument_type,
            any_value(trading_status) AS trading_status,
            max(COALESCE(history_sessions, 0)) AS history_sessions,
            max(COALESCE(listing_age_sessions, 0)) AS listing_age_sessions,
            max(COALESCE(positive_volume_days_60, 0)) AS positive_volume_days_60,
            max(COALESCE(median_traded_value_60, 0)) AS median_traded_value_60,
            max(COALESCE(median_traded_value_126, 0)) AS median_traded_value_126,
            min(rank_126) AS rank_126,
            bool_or(COALESCE(NSE_BROAD_LIQUID_PIT_V1_eligible, false)) AS liquid_v1,
            bool_or(COALESCE(top500_liquidity, false)) AS top500,
            bool_or(COALESCE(top750_liquidity, false)) AS top750,
            bool_or(COALESCE(top1000_liquidity, false)) AS top1000,
            any_value(research_identity_quality) AS research_identity_quality,
            bool_or(COALESCE(research_identity_ok, false)) AS research_identity_ok,
            bool_or(COALESCE(price_adjustment_ok, false)) AS price_adjustment_ok,
            any_value(eligibility_result) AS eligibility_result
          FROM read_parquet('{c}/research_universe_monthly.parquet')
          WHERE CAST(date AS DATE) BETWEEN DATE '{start}' AND DATE '{end}'
          GROUP BY 1, 2
        """)
        union_sql = []
        for flag_name, column in FLAGS:
            base_col = {"LIQUID_V1": "liquid_v1", "TOP500": "top500", "TOP750": "top750", "TOP1000": "top1000"}[flag_name]
            union_sql.append(f"""
              SELECT COALESCE(b.date, c.date) AS date,
                COALESCE(b.symbol_at_date, c.symbol_at_date) AS symbol_at_date,
                '{flag_name}' AS universe_flag,
                COALESCE(b.{base_col}, false) AS baseline_member,
                COALESCE(c.{base_col}, false) AS candidate_member,
                b.security_id AS baseline_security_id,
                c.security_id AS candidate_security_id,
                b.isin AS baseline_isin,
                c.isin AS candidate_isin,
                b.instrument_type AS baseline_instrument_type,
                c.instrument_type AS candidate_instrument_type,
                b.trading_status AS baseline_trading_status,
                c.trading_status AS candidate_trading_status,
                b.history_sessions AS baseline_history_sessions,
                c.history_sessions AS candidate_history_sessions,
                b.listing_age_sessions AS baseline_listing_age_sessions,
                c.listing_age_sessions AS candidate_listing_age_sessions,
                b.positive_volume_days_60 AS baseline_positive_volume_days_60,
                c.positive_volume_days_60 AS candidate_positive_volume_days_60,
                b.median_traded_value_60 AS baseline_median_traded_value_60,
                c.median_traded_value_60 AS candidate_median_traded_value_60,
                b.median_traded_value_126 AS baseline_median_traded_value_126,
                c.median_traded_value_126 AS candidate_median_traded_value_126,
                b.rank_126 AS baseline_rank,
                c.rank_126 AS candidate_rank,
                b.research_identity_quality AS baseline_research_identity_quality,
                c.research_identity_quality AS candidate_research_identity_quality,
                b.research_identity_ok AS baseline_research_identity_ok,
                c.research_identity_ok AS candidate_research_identity_ok,
                b.price_adjustment_ok AS baseline_price_adjustment_ok,
                c.price_adjustment_ok AS candidate_price_adjustment_ok,
                b.eligibility_result AS baseline_eligibility_result,
                c.eligibility_result AS candidate_eligibility_result
              FROM base_monthly b
              FULL OUTER JOIN cand_monthly c USING (date, symbol_at_date)
              WHERE COALESCE(b.{base_col}, false) <> COALESCE(c.{base_col}, false)
            """)
        con.execute("CREATE OR REPLACE TEMP VIEW raw_diffs AS " + " UNION ALL ".join(union_sql))
        con.execute(f"""
          CREATE OR REPLACE TEMP VIEW primary_trigger_rows AS
          SELECT date, universe_flag,
            symbol_at_date AS trigger_symbol,
            COALESCE(baseline_security_id, candidate_security_id) AS trigger_security_id,
              CASE
                WHEN COALESCE(baseline_instrument_type, '') <> 'ORDINARY_EQUITY'
                  OR {' OR '.join([f"symbol_at_date LIKE '%{marker}%'" for marker in NON_ORDINARY_MARKERS])}
                  THEN 'NON_ORDINARY_INSTRUMENT_REMOVAL'
                WHEN candidate_history_sessions IS NOT NULL AND baseline_history_sessions IS NOT NULL
                  AND abs(candidate_history_sessions - baseline_history_sessions) >= 100
                  THEN 'IDENTITY_V2_CONTINUITY_CORRECTION'
                ELSE 'PRIMARY_ELIGIBILITY_CORRECTION'
              END AS trigger_reason
          FROM raw_diffs
          WHERE universe_flag IN ('TOP500', 'TOP750', 'TOP1000')
            AND baseline_member AND NOT candidate_member
        """)
        con.execute("""
          CREATE OR REPLACE TEMP VIEW rank_displacement_triggers AS
          SELECT date, universe_flag,
            CASE
              WHEN baseline_member AND NOT candidate_member THEN 'BASELINE_ONLY'
              WHEN NOT baseline_member AND candidate_member THEN 'CANDIDATE_ONLY'
              ELSE 'CHANGED'
            END AS trigger_side,
            string_agg(symbol_at_date, ', ' ORDER BY symbol_at_date) AS trigger_symbol,
            string_agg(COALESCE(COALESCE(baseline_security_id, candidate_security_id), ''), ', ' ORDER BY symbol_at_date) AS trigger_security_id
          FROM raw_diffs
          WHERE universe_flag IN ('TOP500', 'TOP750', 'TOP1000')
          GROUP BY 1, 2, 3
        """)
        con.execute(f"""
          CREATE OR REPLACE TEMP VIEW attributed AS
          SELECT d.*,
            CASE
              WHEN COALESCE(d.baseline_instrument_type, d.candidate_instrument_type, '') <> 'ORDINARY_EQUITY'
                OR {' OR '.join([f"d.symbol_at_date LIKE '%{marker}%'" for marker in NON_ORDINARY_MARKERS])}
                THEN 'NON_ORDINARY_INSTRUMENT_REMOVAL'
              WHEN d.universe_flag IN ('TOP500', 'TOP750', 'TOP1000')
                AND d.baseline_security_id IS NOT NULL
                AND d.candidate_security_id IS NOT NULL
                AND d.baseline_security_id = d.candidate_security_id
                AND d.baseline_rank IS NOT NULL
                AND d.candidate_rank IS NOT NULL
                AND (
                  (
                    d.baseline_rank <= CASE d.universe_flag WHEN 'TOP500' THEN 500 WHEN 'TOP750' THEN 750 ELSE 1000 END
                    AND d.candidate_rank > CASE d.universe_flag WHEN 'TOP500' THEN 500 WHEN 'TOP750' THEN 750 ELSE 1000 END
                  )
                  OR (
                    d.candidate_rank <= CASE d.universe_flag WHEN 'TOP500' THEN 500 WHEN 'TOP750' THEN 750 ELSE 1000 END
                    AND d.baseline_rank > CASE d.universe_flag WHEN 'TOP500' THEN 500 WHEN 'TOP750' THEN 750 ELSE 1000 END
                  )
                )
                THEN 'RANK_CUTOFF_SECOND_ORDER_EFFECT'
              WHEN d.universe_flag IN ('TOP500', 'TOP750', 'TOP1000')
                AND NOT d.baseline_member AND d.candidate_member
                AND t.trigger_symbol IS NOT NULL
                THEN 'RANK_CUTOFF_SECOND_ORDER_EFFECT'
              WHEN d.baseline_security_id IS NOT NULL AND d.candidate_security_id IS NOT NULL
                AND d.baseline_security_id <> d.candidate_security_id
                THEN 'IDENTITY_V2_CONTINUITY_CORRECTION'
              WHEN d.baseline_isin IS NOT NULL AND d.candidate_isin IS NOT NULL
                AND d.baseline_isin <> d.candidate_isin
                THEN 'IDENTITY_V2_CONTINUITY_CORRECTION'
              WHEN d.candidate_history_sessions IS NOT NULL AND d.baseline_history_sessions IS NOT NULL
                AND abs(d.candidate_history_sessions - d.baseline_history_sessions) >= 100
                THEN 'IDENTITY_V2_CONTINUITY_CORRECTION'
              WHEN d.universe_flag = 'LIQUID_V1'
                AND d.baseline_listing_age_sessions IS NOT NULL
                AND d.candidate_listing_age_sessions IS NOT NULL
                AND (
                  (d.baseline_listing_age_sessions >= 272 AND d.candidate_listing_age_sessions < 272)
                  OR (d.candidate_listing_age_sessions >= 272 AND d.baseline_listing_age_sessions < 272)
                )
                THEN 'SESSION_CORRECT_HISTORY_RECALCULATION'
              WHEN d.candidate_listing_age_sessions IS NOT NULL AND d.baseline_listing_age_sessions IS NOT NULL
                AND abs(d.candidate_listing_age_sessions - d.baseline_listing_age_sessions) >= 100
                THEN 'LISTING_HISTORY_CONTINUITY_CORRECTION'
              WHEN d.baseline_trading_status IS DISTINCT FROM d.candidate_trading_status
                THEN 'TRADING_STATUS_CORRECTION'
              WHEN d.candidate_positive_volume_days_60 IS NOT NULL AND d.baseline_positive_volume_days_60 IS NOT NULL
                AND abs(d.candidate_positive_volume_days_60 - d.baseline_positive_volume_days_60) >= 5
                THEN 'POSITIVE_VOLUME_RULE_CORRECTION'
              WHEN d.candidate_median_traded_value_60 IS NOT NULL AND d.baseline_median_traded_value_60 IS NOT NULL
                AND abs(d.candidate_median_traded_value_60 - d.baseline_median_traded_value_60) > 1000000
                THEN 'SESSION_CORRECT_LIQUIDITY_RECALCULATION'
              WHEN d.candidate_median_traded_value_126 IS NOT NULL AND d.baseline_median_traded_value_126 IS NOT NULL
                AND abs(d.candidate_median_traded_value_126 - d.baseline_median_traded_value_126) > 1000000
                THEN 'SESSION_CORRECT_LIQUIDITY_RECALCULATION'
              WHEN d.baseline_price_adjustment_ok IS DISTINCT FROM d.candidate_price_adjustment_ok
                THEN 'CORPORATE_ACTION_ADJUSTMENT_CORRECTION'
              WHEN d.baseline_security_id IS NULL AND d.candidate_security_id IS NOT NULL
                THEN 'ADDED_OFFICIAL_SOURCE_RECORD'
              WHEN d.baseline_security_id IS NOT NULL AND d.candidate_security_id IS NULL
                THEN 'SOURCE_OBSERVATION_CORRECTION'
              ELSE 'UNEXPLAINED'
            END AS primary_attribution,
            CASE
              WHEN d.baseline_member AND NOT d.candidate_member THEN 'BASELINE_ONLY'
              WHEN NOT d.baseline_member AND d.candidate_member THEN 'CANDIDATE_ONLY'
              ELSE 'CHANGED'
            END AS diff_side,
            CASE
              WHEN d.universe_flag IN ('TOP500', 'TOP750', 'TOP1000')
                AND COALESCE(d.baseline_member, false) <> COALESCE(d.candidate_member, false)
                AND t.trigger_symbol IS NOT NULL
                THEN t.trigger_symbol
              ELSE NULL
            END AS trigger_symbol,
            CASE
              WHEN d.universe_flag IN ('TOP500', 'TOP750', 'TOP1000')
                AND COALESCE(d.baseline_member, false) <> COALESCE(d.candidate_member, false)
                AND t.trigger_security_id IS NOT NULL
                THEN t.trigger_security_id
              ELSE NULL
            END AS trigger_security_id,
            CASE
              WHEN d.universe_flag IN ('TOP500', 'TOP750', 'TOP1000')
                AND COALESCE(d.baseline_member, false) <> COALESCE(d.candidate_member, false)
                AND t.trigger_symbol IS NOT NULL
                THEN 'OPPOSITE_SIDE_RANK_BOUNDARY_DIFF_SET'
              ELSE NULL
            END AS trigger_reason
          FROM raw_diffs d
          LEFT JOIN rank_displacement_triggers t
            ON t.date = d.date
           AND t.universe_flag = d.universe_flag
           AND t.trigger_side = CASE
              WHEN d.baseline_member AND NOT d.candidate_member THEN 'CANDIDATE_ONLY'
              WHEN NOT d.baseline_member AND d.candidate_member THEN 'BASELINE_ONLY'
              ELSE 'CHANGED'
            END
        """)
        con.execute(f"COPY attributed TO '{o}' (FORMAT PARQUET)")
        con.execute(f"""
          CREATE OR REPLACE TEMP VIEW signal_diffs AS
          WITH baseline_prices AS (
            SELECT CAST(date AS DATE) AS date, security_id, UPPER(symbol_at_date) AS symbol_at_date,
              research_adjusted_close AS baseline_value
            FROM read_parquet('{b}/daily_prices_adjusted.parquet')
            WHERE CAST(date AS DATE) BETWEEN DATE '{start}' AND DATE '{end}'
          ), candidate_prices AS (
            SELECT CAST(date AS DATE) AS date, security_id, UPPER(symbol_at_date) AS symbol_at_date,
              research_adjusted_close AS candidate_value
            FROM read_parquet('{c}/daily_prices_adjusted.parquet')
            WHERE CAST(date AS DATE) BETWEEN DATE '{start}' AND DATE '{end}'
          ), added_actions AS (
            SELECT c.security_id, CAST(c.event_date AS DATE) AS event_date, c.event_id, c.event_type
            FROM read_parquet('{c}/corporate_actions.parquet') c
            LEFT JOIN read_parquet('{b}/corporate_actions.parquet') p
              ON p.security_id = c.security_id
             AND CAST(p.event_date AS DATE) = CAST(c.event_date AS DATE)
             AND p.event_type = c.event_type
            WHERE CAST(c.event_date AS DATE) BETWEEN DATE '{start}' AND DATE '{end}'
              AND c.event_type IN ('SPLIT', 'REVERSE_SPLIT', 'BONUS', 'BONUS_RIGHTS_COMPOSITE', 'SELECTIVE_BONUS')
              AND c.price_factor IS NOT NULL
              AND p.security_id IS NULL
          )
          SELECT COALESCE(b.date, c.date) AS date,
            COALESCE(b.symbol_at_date, c.symbol_at_date) AS symbol,
            COALESCE(b.security_id, c.security_id) AS security_id,
            b.baseline_value,
            c.candidate_value,
            abs(COALESCE(b.baseline_value, 0) - COALESCE(c.candidate_value, 0)) AS absolute_difference,
            CASE WHEN b.baseline_value IS NOT NULL AND b.baseline_value <> 0 THEN (c.candidate_value / b.baseline_value) - 1 ELSE NULL END AS relative_difference,
            CASE
              WHEN b.security_id IS NOT NULL AND c.security_id IS NOT NULL
                AND EXISTS (SELECT 1 FROM added_actions a WHERE a.security_id = c.security_id AND a.event_date > c.date)
                THEN 'ADDED_OFFICIAL_MATERIAL_ACTION_FORWARD_FACTOR'
              WHEN b.security_id IS NULL OR c.security_id IS NULL
                THEN 'IDENTITY_RECONSTRUCTION_OR_SOURCE_SCOPE'
              ELSE 'UNEXPLAINED'
            END AS cause,
            (SELECT any_value(a.event_id) FROM added_actions a WHERE a.security_id = COALESCE(c.security_id, b.security_id) AND a.event_date > COALESCE(c.date, b.date)) AS related_corporate_action
          FROM baseline_prices b
          JOIN candidate_prices c USING (date, security_id)
          WHERE abs(COALESCE(b.baseline_value, -1) - COALESCE(c.candidate_value, -1)) > 0.000001
        """)
        con.execute(f"COPY signal_diffs TO '{so}' (FORMAT PARQUET)")
        summary_rows = con.execute("""
          SELECT universe_flag, primary_attribution, COUNT(*) AS rows
          FROM attributed
          GROUP BY 1, 2
          ORDER BY 1, 2
        """).fetchall()
        totals = dict(con.execute("SELECT universe_flag, COUNT(*) FROM attributed GROUP BY 1").fetchall())
        unexplained = dict(con.execute("SELECT universe_flag, COUNT(*) FROM attributed WHERE primary_attribution = 'UNEXPLAINED' GROUP BY 1").fetchall())
        signal_totals = con.execute("""
          SELECT COUNT(*) AS total,
            COUNT(*) FILTER (WHERE cause <> 'UNEXPLAINED') AS explained,
            COUNT(*) FILTER (WHERE cause = 'UNEXPLAINED') AS unexplained
          FROM signal_diffs
        """).fetchone()
        signal_causes = con.execute("SELECT cause, COUNT(*) FROM signal_diffs GROUP BY 1 ORDER BY 1").fetchall()
        top_symbols = con.execute("""
          SELECT universe_flag, symbol_at_date, COUNT(*) AS rows
          FROM attributed
          GROUP BY 1, 2
          ORDER BY rows DESC, universe_flag, symbol_at_date
          LIMIT 25
        """).fetchall()
        by_year = con.execute("""
          SELECT universe_flag, year(date) AS year, COUNT(*) AS rows
          FROM attributed
          GROUP BY 1, 2
          ORDER BY 1, 2
        """).fetchall()
        rank_chains = con.execute("""
          SELECT date, universe_flag, trigger_symbol, trigger_security_id, trigger_reason,
            symbol_at_date AS affected_symbol, baseline_rank, candidate_rank
          FROM attributed
          WHERE primary_attribution = 'RANK_CUTOFF_SECOND_ORDER_EFFECT'
          ORDER BY date, universe_flag, affected_symbol
          LIMIT 25
        """).fetchall()
        examples = con.execute("""
          SELECT date, symbol_at_date, universe_flag, diff_side, primary_attribution,
            baseline_history_sessions, candidate_history_sessions,
            baseline_median_traded_value_60, candidate_median_traded_value_60,
            baseline_rank, candidate_rank,
            trigger_symbol, trigger_reason
          FROM attributed
          ORDER BY primary_attribution, date, symbol_at_date, universe_flag
          LIMIT 40
        """).fetchall()
    finally:
        con.close()
    summary = {
        "artifact_sha256": sha256(out),
        "signal_artifact_sha256": sha256(signal_out),
        "totals": {str(k): int(v) for k, v in totals.items()},
        "unexplained": {str(k): int(v) for k, v in unexplained.items()},
        "attribution_counts": [
            {"universe_flag": flag, "primary_attribution": attr, "rows": int(rows)}
            for flag, attr, rows in summary_rows
        ],
        "signal_price": {
            "total": int(signal_totals[0]),
            "explained": int(signal_totals[1]),
            "unexplained": int(signal_totals[2]),
            "cause_counts": [{"cause": cause, "rows": int(rows)} for cause, rows in signal_causes],
        },
        "top_symbols": [{"universe_flag": flag, "symbol": symbol, "rows": int(rows)} for flag, symbol, rows in top_symbols],
        "by_year": [{"universe_flag": flag, "year": int(year), "rows": int(rows)} for flag, year, rows in by_year],
        "rank_chains": [
            {
                "date": str(date),
                "universe_flag": flag,
                "trigger_symbol": trigger_symbol,
                "trigger_security_id": trigger_security_id,
                "trigger_reason": trigger_reason,
                "affected_symbol": affected_symbol,
                "baseline_rank": None if baseline_rank is None else int(baseline_rank),
                "candidate_rank": None if candidate_rank is None else int(candidate_rank),
            }
            for date, flag, trigger_symbol, trigger_security_id, trigger_reason, affected_symbol, baseline_rank, candidate_rank in rank_chains
        ],
        "examples": [
            {
                "date": str(date),
                "symbol": symbol,
                "universe_flag": flag,
                "diff_side": side,
                "primary_attribution": attr,
                "baseline_history_sessions": None if bh is None else int(bh),
                "candidate_history_sessions": None if ch is None else int(ch),
                "baseline_median_traded_value_60": bm,
                "candidate_median_traded_value_60": cm,
                "baseline_rank": None if br is None else int(br),
                "candidate_rank": None if cr is None else int(cr),
                "trigger_symbol": trigger_symbol,
                "trigger_reason": trigger_reason,
            }
            for date, symbol, flag, side, attr, bh, ch, bm, cm, br, cr, trigger_symbol, trigger_reason in examples
        ],
    }
    return summary


def write_report(summary: dict[str, Any], report: Path, *, baseline: Path, candidate: Path, artifact: Path, signal_artifact: Path) -> None:
    totals = summary["totals"]
    unexplained = summary["unexplained"]
    lines = [
        "# v2.0.1 membership regression attribution",
        "",
        f"Baseline release: `{baseline}`.",
        f"Candidate release: `{candidate}`.",
        f"Difference artifact: `{artifact}`.",
        f"Signal-price difference artifact: `{signal_artifact}`.",
        f"Difference artifact SHA256: `{summary['artifact_sha256']}`.",
        f"Signal artifact SHA256: `{summary['signal_artifact_sha256']}`.",
        "",
        "## Reconciliation",
        "",
        "| Universe | Total differences | Attributed | Unexplained |",
        "|---|---:|---:|---:|",
    ]
    for flag in ("LIQUID_V1", "TOP500", "TOP750", "TOP1000"):
        total = int(totals.get(flag, 0))
        bad = int(unexplained.get(flag, 0))
        lines.append(f"| `{flag}` | {total} | {total - bad} | {bad} |")
    lines.extend([
        "",
        "## Attribution counts",
        "",
        "| Universe | Attribution | Rows |",
        "|---|---|---:|",
    ])
    for row in summary["attribution_counts"]:
        lines.append(f"| `{row['universe_flag']}` | `{row['primary_attribution']}` | {row['rows']} |")
    lines.extend([
        "",
        "## Differences by year",
        "",
        "| Universe | Year | Rows |",
        "|---|---:|---:|",
    ])
    for row in summary["by_year"]:
        lines.append(f"| `{row['universe_flag']}` | {row['year']} | {row['rows']} |")
    lines.extend([
        "",
        "## Top affected symbols",
        "",
        "| Universe | Symbol | Rows |",
        "|---|---|---:|",
    ])
    for row in summary["top_symbols"]:
        lines.append(f"| `{row['universe_flag']}` | `{row['symbol']}` | {row['rows']} |")
    lines.extend([
        "",
        "## Rank displacement chains",
        "",
        "| Date | Universe | Trigger | Trigger reason | Affected symbol | Baseline rank | Candidate rank |",
        "|---|---|---|---|---|---:|---:|",
    ])
    for row in summary["rank_chains"]:
        lines.append(f"| {row['date']} | `{row['universe_flag']}` | `{row['trigger_symbol']}` | `{row['trigger_reason']}` | `{row['affected_symbol']}` | {row['baseline_rank']} | {row['candidate_rank']} |")
    lines.extend([
        "",
        "## Representative examples",
        "",
        "| Date | Symbol | Universe | Side | Attribution | Baseline history | Candidate history | Baseline MTV60 | Candidate MTV60 | Trigger |",
        "|---|---|---|---|---|---:|---:|---:|---:|---|",
    ])
    for row in summary["examples"]:
        lines.append(f"| {row['date']} | `{row['symbol']}` | `{row['universe_flag']}` | `{row['diff_side']}` | `{row['primary_attribution']}` | {row['baseline_history_sessions']} | {row['candidate_history_sessions']} | {row['baseline_median_traded_value_60']} | {row['candidate_median_traded_value_60']} | `{row['trigger_symbol'] or ''}` |")
    signal = summary["signal_price"]
    lines.extend([
        "",
        "## Signal-price differences",
        "",
        f"Matched/economic signal-price differences: `{signal['total']}`.",
        f"Explained: `{signal['explained']}`.",
        f"Unexplained: `{signal['unexplained']}`.",
        "",
        "| Cause | Rows |",
        "|---|---:|",
    ])
    for row in signal["cause_counts"]:
        lines.append(f"| `{row['cause']}` | {row['rows']} |")
    lines.extend([
        "",
        "## Unexplained rows",
        "",
        "Unexplained rows are a fail-closed state. Current count is `0` when all universe rows above reconcile with `Unexplained = 0`.",
    ])
    status = "PASS" if all(int(v) == 0 for v in unexplained.values()) and signal["unexplained"] == 0 else "REVIEW_REQUIRED"
    lines.extend(["", f"Attribution status: `{status}`."])
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-release", default="releases/india_equity_data_v2.0.1")
    parser.add_argument("--candidate-release", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--signal-out", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()
    baseline = Path(args.baseline_release)
    candidate = Path(args.candidate_release)
    out = Path(args.out)
    signal_out = Path(args.signal_out)
    summary = build_differences(baseline, candidate, out, signal_out)
    write_report(summary, Path(args.report), baseline=baseline, candidate=candidate, artifact=out, signal_artifact=signal_out)
    Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
    Path(args.summary).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS" if not any(summary["unexplained"].values()) and summary["signal_price"]["unexplained"] == 0 else "REVIEW_REQUIRED", "totals": summary["totals"], "signal_price": summary["signal_price"]}, sort_keys=True))
    if any(summary["unexplained"].values()) or summary["signal_price"]["unexplained"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
