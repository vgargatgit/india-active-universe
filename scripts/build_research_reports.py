#!/usr/bin/env python3
"""Create scoped Phase 2 reports and the downstream research manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import duckdb

from india_active_universe.profiles import (
    ADJUSTED_PRICE_ARTIFACT,
    CANDIDATE_AUDIT_NOT_RECORDED_INTERPRETATION,
    CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS,
    CANDIDATE_DECISION_GATE_KEYS,
    CANDIDATE_GATE_PASS_INTERPRETATION,
    CANDIDATE_NOT_MATERIALIZED_INTERPRETATION,
    CANDIDATE_NOT_READY_INTERPRETATION,
    CANDIDATE_NUMERIC_HARD_FAILURE_KEYS,
    CANDIDATE_FAIL_VALUE,
    CANDIDATE_FEATURE_READINESS_POLICY,
    CANDIDATE_NOT_RECORDED_VALUE,
    CANDIDATE_PASS_VALUE,
    CANDIDATE_PIT_UNIVERSE_INTERVAL_TYPE,
    CANDIDATE_REFINED_BOUNDARY_SCAN_METHOD,
    CANDIDATE_RESEARCH_START_DATES,
    CORPORATE_ACTIONS_ARTIFACT,
    CURRENT_PROVEN_RESEARCH_END_DATE,
    CURRENT_PROVEN_RESEARCH_START_DATE,
    DATA_RELEASE_MANIFEST_ARTIFACT,
    EXECUTION_POLICY,
    FEATURE_READINESS_WINDOWS,
    LIQUIDITY_ARTIFACT,
    LIQUID_V1_DEFINITION,
    PARTITIONED_ARTIFACTS_MANIFEST,
    PRIORITY_SCOPE,
    PROFILE_ID,
    PROFILE_VERSION,
    RAW_EXECUTION_PRICE_ARTIFACT,
    RECOMMENDED_SIGNAL_PRICE_SERIES,
    RESEARCH_RELEASE_MANIFEST_ARTIFACT,
    RESEARCH_MANIFEST_ARTIFACTS,
    RESEARCH_UNIVERSE_MONTHLY_ARTIFACT,
    RESEARCH_EXPLORATORY_STATUS,
    RESEARCH_HIGH_CONFIDENCE_STATUS,
    RESEARCH_MONTHLY_SNAPSHOT_START,
    RESEARCH_START_DATE,
    REQUIRED_RESEARCH_REPORTS,
    REQUIRED_QUALITY_THRESHOLD,
    SIGNAL_POLICY,
    SOURCE_ONLY_STATUS,
    TERMINAL_VALUE_POLICY,
    TERMINAL_VALUE_POLICY_REQUIREMENT,
    TOP_LIQUIDITY_RANKING_METRIC,
)


MATERIAL_ACTIONS = "('SPLIT', 'REVERSE_SPLIT', 'BONUS')"

def path_sql(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def published_research_quality_bounds(
    research_quality_intervals: list[dict],
    *,
    fallback_start: str,
    fallback_end: str | None,
) -> tuple[str, str | None]:
    """Return the scalar research bounds backed by published RHC interval evidence."""
    published_rhc_intervals = sorted(
        (
            interval for interval in research_quality_intervals
            if isinstance(interval, dict)
            and interval.get("status") == RESEARCH_HIGH_CONFIDENCE_STATUS
            and interval.get("profile") == PROFILE_ID
            and interval.get("profile_version") == PROFILE_VERSION
            and interval.get("priority_scope") == PRIORITY_SCOPE
            and interval.get("start")
        ),
        key=lambda interval: interval["start"],
    )
    if not published_rhc_intervals:
        return fallback_start, fallback_end
    return published_rhc_intervals[0]["start"], published_rhc_intervals[0].get("end") or fallback_end


def published_research_monthly_snapshot_start(
    published_start: str,
    *,
    fallback_start: str,
    fallback_monthly_start: str,
) -> str:
    """Return the first monthly snapshot covered by the scalar research interval."""
    if published_start == CURRENT_PROVEN_RESEARCH_START_DATE:
        return RESEARCH_MONTHLY_SNAPSHOT_START
    if published_start == fallback_start:
        return fallback_monthly_start
    return published_start


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def validation_passed(path: Path) -> bool:
    if not path.exists():
        return False
    return json.loads(path.read_text(encoding="utf-8")).get("status") == "PASS"


def ci_passed(path: Path, *, git_sha: str) -> bool:
    if not path.exists():
        return False
    status = json.loads(path.read_text(encoding="utf-8"))
    return (
        status.get("status") == "completed"
        and status.get("conclusion") == "success"
        and status.get("head_sha") == git_sha
    )


def junit_passed(path: Path) -> bool:
    if not path.exists():
        return False
    root = ET.parse(path).getroot()
    suites = list(root.iter("testsuite"))
    if not suites:
        return False
    failures = sum(int(suite.get("failures", "0")) for suite in suites)
    errors = sum(int(suite.get("errors", "0")) for suite in suites)
    return failures == 0 and errors == 0


def scalar(connection: duckdb.DuckDBPyConnection, query: str):
    return connection.execute(query).fetchone()[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--reports", default="reports")
    parser.add_argument("--baseline-release", default="releases/india_equity_data_v2.0.1")
    parser.add_argument("--config", default="config/default.yaml")
    parser.add_argument("--manual-overrides", default="data/reference/manual_identity_overrides.yaml")
    parser.add_argument("--promote-research-start")
    parser.add_argument("--promote-monthly-start")
    args = parser.parse_args()
    release = Path(args.release)
    reports = Path(args.reports)
    r = path_sql(release)
    baseline_release = Path(args.baseline_release)
    baseline_r = path_sql(baseline_release)
    release_manifest = json.loads((release / DATA_RELEASE_MANIFEST_ARTIFACT).read_text(encoding="utf-8"))
    observed_coverage = release_manifest.get("coverage", {})
    research_coverage = release_manifest.get("research_coverage", {})
    research_start = research_coverage.get("research_verified_start", RESEARCH_START_DATE)
    research_monthly_start = research_coverage.get("monthly_snapshot_start") or RESEARCH_MONTHLY_SNAPSHOT_START
    warmup_coverage = release_manifest.get("warmup_coverage", {})
    research_quality_intervals = release_manifest.get("research_quality_intervals", [])
    if args.promote_research_start:
        promoted_interval = {
            "start": args.promote_research_start,
            "end": str(observed_coverage.get("observed_end")),
            "status": RESEARCH_HIGH_CONFIDENCE_STATUS,
            "profile": PROFILE_ID,
            "profile_version": PROFILE_VERSION,
            "priority_scope": PRIORITY_SCOPE,
        }
        research_quality_intervals = [
            interval for interval in research_quality_intervals
            if not (
                isinstance(interval, dict)
                and interval.get("status") == RESEARCH_HIGH_CONFIDENCE_STATUS
                and interval.get("profile") == PROFILE_ID
                and interval.get("profile_version") == PROFILE_VERSION
                and interval.get("priority_scope") == PRIORITY_SCOPE
            )
        ]
        research_quality_intervals.insert(0, promoted_interval)
    published_research_start, published_research_end = published_research_quality_bounds(
        research_quality_intervals,
        fallback_start=research_start,
        fallback_end=str(observed_coverage.get("observed_end")),
    )
    published_research_monthly_start = args.promote_monthly_start or published_research_monthly_snapshot_start(
        published_research_start,
        fallback_start=research_start,
        fallback_monthly_start=research_monthly_start,
    )
    connection = duckdb.connect()
    try:
        counts = connection.execute(f"""
          SELECT COUNT(*) AS rows,
            COUNT(DISTINCT security_id) AS securities,
            COUNT(DISTINCT date) AS months,
            COUNT(DISTINCT security_id) FILTER (WHERE NSE_BROAD_LIQUID_PIT_V1_eligible) AS liquid_securities,
            COUNT(DISTINCT security_id) FILTER (WHERE top750_liquidity) AS top750_securities,
            COUNT(DISTINCT security_id) FILTER (WHERE NSE_BROAD_LIQUID_PIT_V1_eligible AND NOT research_identity_ok) AS identity_failures
          FROM read_parquet('{r}/research_universe_monthly.parquet')
        """).fetchone()
        year_rows = connection.execute(f"""
          SELECT EXTRACT(YEAR FROM date)::INTEGER AS year,
            COUNT(DISTINCT security_id) AS active_ordinary,
            COUNT(DISTINCT security_id) FILTER (WHERE NSE_BROAD_LIQUID_PIT_V1_eligible) AS liquid_v1,
            COUNT(DISTINCT security_id) FILTER (WHERE top750_liquidity) AS top750,
            COUNT(DISTINCT security_id) FILTER (WHERE NOT research_identity_ok) AS identity_failures,
            COUNT(DISTINCT security_id) FILTER (WHERE absent_observation_days_60 > 0) AS sparse_observation_names
          FROM read_parquet('{r}/research_universe_monthly.parquet')
          GROUP BY 1 ORDER BY 1
        """).fetchall()
        identity_rows = connection.execute(f"""
          SELECT research_identity_quality, COUNT(DISTINCT security_id)
          FROM read_parquet('{r}/research_universe_monthly.parquet')
          WHERE CAST(date AS DATE) >= DATE '{research_start}'
            AND (NSE_BROAD_LIQUID_PIT_V1_eligible OR top750_liquidity)
          GROUP BY 1 ORDER BY 1
        """).fetchall()
        adjustment_rows = connection.execute(f"""
          WITH promoted_required AS (
            SELECT DISTINCT security_id
            FROM read_parquet('{r}/research_universe_monthly.parquet')
            WHERE CAST(date AS DATE) >= DATE '{research_start}'
              AND (NSE_BROAD_LIQUID_PIT_V1_eligible OR top750_liquidity)
          )
          SELECT adjustment_quality, COUNT(*)
          FROM read_parquet('{r}/daily_prices_adjusted.parquet') p
          JOIN promoted_required q USING (security_id)
          WHERE CAST(p.date AS DATE) >= DATE '{research_start}'
          GROUP BY 1 ORDER BY 1
        """).fetchall()
        event_rows = connection.execute(f"""
          WITH promoted_required AS (
            SELECT DISTINCT security_id
            FROM read_parquet('{r}/research_universe_monthly.parquet')
            WHERE CAST(date AS DATE) >= DATE '{research_start}'
              AND (NSE_BROAD_LIQUID_PIT_V1_eligible OR top750_liquidity)
          )
          SELECT ca.event_type, COUNT(*) AS events,
            COUNT(*) FILTER (WHERE ca.price_factor IS NULL OR ca.share_factor IS NULL) AS missing_factors
          FROM read_parquet('{r}/corporate_actions.parquet') ca
          JOIN promoted_required q USING (security_id)
          WHERE ca.event_type IN {MATERIAL_ACTIONS}
            AND CAST(ca.event_date AS DATE) >= DATE '{research_start}'
          GROUP BY 1 ORDER BY 1
        """).fetchall()
        event_detail_rows = connection.execute(f"""
          WITH promoted_required AS (
            SELECT DISTINCT security_id
            FROM read_parquet('{r}/research_universe_monthly.parquet')
            WHERE CAST(date AS DATE) >= DATE '{research_start}'
              AND (NSE_BROAD_LIQUID_PIT_V1_eligible OR top750_liquidity)
          )
          SELECT ca.security_id, ca.symbol_at_event, ca.event_date, ca.event_type,
            ca.price_factor, ca.share_factor, v.pre_event_close, v.post_event_close,
            CASE WHEN v.pre_event_close IS NOT NULL AND v.pre_event_close <> 0 AND v.post_event_close IS NOT NULL
              THEN v.post_event_close / v.pre_event_close - 1 END AS raw_boundary_return,
            CASE WHEN v.pre_event_close IS NOT NULL AND v.pre_event_close <> 0 AND v.post_event_close IS NOT NULL AND ca.price_factor IS NOT NULL AND ca.price_factor <> 0
              THEN v.post_event_close / (v.pre_event_close * ca.price_factor) - 1 END AS adjusted_boundary_return,
            v.holder_value_ratio, v.validation_status
          FROM read_parquet('{r}/corporate_actions.parquet') ca
          JOIN promoted_required q USING (security_id)
          LEFT JOIN read_parquet('{r}/corporate_action_boundary_validation.parquet') v
            ON v.event_id = ca.event_id
          WHERE ca.event_type IN {MATERIAL_ACTIONS}
            AND CAST(ca.event_date AS DATE) >= DATE '{research_start}'
          ORDER BY CAST(ca.event_date AS DATE), ca.security_id
        """).fetchall()
        boundary_rows = connection.execute(f"""
          WITH promoted_required AS (
            SELECT DISTINCT security_id
            FROM read_parquet('{r}/research_universe_monthly.parquet')
            WHERE CAST(date AS DATE) >= DATE '{research_start}'
              AND (NSE_BROAD_LIQUID_PIT_V1_eligible OR top750_liquidity)
          )
          SELECT v.validation_status, COUNT(DISTINCT v.event_id)
          FROM read_parquet('{r}/corporate_action_boundary_validation.parquet') v
          JOIN promoted_required q USING (security_id)
          WHERE CAST(v.ex_date AS DATE) >= DATE '{research_start}'
          GROUP BY 1 ORDER BY 1
        """).fetchall()
        unresolved_boundary_count = scalar(connection, f"""
          WITH promoted_required AS (
            SELECT DISTINCT security_id
            FROM read_parquet('{r}/research_universe_monthly.parquet')
            WHERE CAST(date AS DATE) >= DATE '{research_start}'
              AND (NSE_BROAD_LIQUID_PIT_V1_eligible OR top750_liquidity)
          )
          SELECT COUNT(DISTINCT v.event_id)
          FROM read_parquet('{r}/corporate_action_boundary_validation.parquet') v
          JOIN promoted_required q USING (security_id)
          WHERE CAST(v.ex_date AS DATE) >= DATE '{research_start}'
            AND v.validation_status IN (
              'WARNING_LARGE_BOUNDARY_MOVE',
              'INVALID_PRE_EVENT_PRICE',
              'NO_BOUNDARY_OBSERVATIONS',
              'NO_LOCAL_BOUNDARY_OBSERVATION'
            )
        """)
        status_overlap = scalar(connection, f"""
          SELECT COUNT(*) FROM (
            SELECT security_id, status_start,
              LAG(status_end) OVER (PARTITION BY security_id ORDER BY status_start) AS previous_end
            FROM read_parquet('{r}/trading_status_intervals.parquet')
          ) WHERE previous_end IS NOT NULL AND status_start <= previous_end
        """)
        max_absent = scalar(connection, f"SELECT COALESCE(MAX(absent_observation_days_60), 0) FROM read_parquet('{r}/research_universe_monthly.parquet')")
        required_count = scalar(connection, f"SELECT COUNT(*) FROM read_parquet('{r}/required_research_security.parquet')")
        promoted_required_count = scalar(connection, f"""
          SELECT COUNT(DISTINCT security_id)
          FROM read_parquet('{r}/research_universe_monthly.parquet')
          WHERE CAST(date AS DATE) >= DATE '{research_start}'
            AND (NSE_BROAD_LIQUID_PIT_V1_eligible OR top750_liquidity)
        """)
        promoted_liquid_count = scalar(connection, f"""
          SELECT COUNT(DISTINCT security_id)
          FROM read_parquet('{r}/research_universe_monthly.parquet')
          WHERE CAST(date AS DATE) >= DATE '{research_start}'
            AND NSE_BROAD_LIQUID_PIT_V1_eligible
        """)
        promoted_top750_count = scalar(connection, f"""
          SELECT COUNT(DISTINCT security_id)
          FROM read_parquet('{r}/research_universe_monthly.parquet')
          WHERE CAST(date AS DATE) >= DATE '{research_start}'
            AND top750_liquidity
        """)
        coverage = connection.execute(f"SELECT MIN(date), MAX(date) FROM read_parquet('{r}/research_universe_monthly.parquet')").fetchone()
        calendar_dates = [str(row[0]) for row in connection.execute(f"SELECT CAST(date AS DATE) FROM read_parquet('{r}/trading_calendar.parquet') ORDER BY 1").fetchall()]
        monthly_detail_rows = connection.execute(f"""
          SELECT date, security_id, NSE_BROAD_LIQUID_PIT_V1_eligible, top750_liquidity,
                 top500_liquidity, top1000_liquidity
          FROM read_parquet('{r}/research_universe_monthly.parquet')
        """).fetchall()
        identity_priority_rows = connection.execute(f"""
          WITH required_monthly AS (
            SELECT *
            FROM read_parquet('{r}/research_universe_monthly.parquet')
            WHERE NSE_BROAD_LIQUID_PIT_V1_eligible OR top750_liquidity
          )
          SELECT q.security_id,
            MIN(m.symbol) AS symbol,
            MIN(m.company_name) AS company_name,
            MIN(m.first_seen) AS first_seen,
            MAX(m.last_seen) AS last_seen,
            MAX(u.liquidity_rank_126) AS max_liquidity_rank_126,
            COUNT(DISTINCT u.date) FILTER (WHERE u.NSE_BROAD_LIQUID_PIT_V1_eligible) AS liquid_dates,
            MIN(m.identity_quality) AS identity_quality,
            STRING_AGG(DISTINCT m.isin, ', ') FILTER (WHERE m.isin IS NOT NULL) AS isin_evidence,
            COUNT(DISTINCT m.company_name) AS company_name_count,
            COUNT(DISTINCT m.symbol) AS symbol_count,
            MAX(u.absent_observation_days_60) AS max_absent_days_60,
            MIN(CASE WHEN u.research_identity_ok THEN 1 ELSE 0 END)::BOOLEAN AS research_identity_ok
          FROM read_parquet('{r}/required_research_security.parquet') q
          JOIN read_parquet('{r}/security_master.parquet') m USING (security_id)
          LEFT JOIN required_monthly u USING (security_id)
          GROUP BY q.security_id
          ORDER BY max_liquidity_rank_126 NULLS LAST, q.security_id
        """).fetchall()
        pre2013_identity_priority_rows = connection.execute(f"""
          WITH required_monthly AS (
            SELECT *
            FROM read_parquet('{r}/research_universe_monthly.parquet')
            WHERE CAST(date AS DATE) < DATE '{CURRENT_PROVEN_RESEARCH_START_DATE}'
              AND (NSE_BROAD_LIQUID_PIT_V1_eligible OR top750_liquidity)
          ), episode_counts AS (
            SELECT security_id, COUNT(DISTINCT listing_episode_id) AS episode_count
            FROM read_parquet('{r}/security_master.parquet')
            GROUP BY security_id
          )
          SELECT u.security_id,
            MIN(u.symbol_at_date) AS symbol,
            MIN(u.company_name) AS company_name,
            MIN(CAST(u.date AS DATE)) AS first_research_month,
            MAX(CAST(u.date AS DATE)) AS last_research_month,
            STRING_AGG(DISTINCT u.isin, ', ') FILTER (WHERE u.isin IS NOT NULL) AS candidate_isin,
            MIN(u.research_identity_quality) AS research_identity_quality,
            MIN(u.liquidity_rank_126) AS best_liquidity_rank_126,
            COUNT(DISTINCT u.date) AS research_months,
            COALESCE(MAX(e.episode_count), 0) AS episode_count,
            MAX(u.absent_observation_days_60) AS max_absent_days_60,
            COUNT(DISTINCT u.company_name) AS company_name_variants,
            MIN(CASE WHEN u.research_identity_ok THEN 1 ELSE 0 END)::BOOLEAN AS research_identity_ok
          FROM required_monthly u
          LEFT JOIN episode_counts e USING (security_id)
          GROUP BY u.security_id
          ORDER BY research_identity_ok, best_liquidity_rank_126 NULLS LAST, research_months DESC, u.security_id
        """).fetchall()
        pre2013_episode_audit_rows = connection.execute(f"""
          WITH pre2013_required AS (
            SELECT DISTINCT security_id
            FROM read_parquet('{r}/research_universe_monthly.parquet')
            WHERE CAST(date AS DATE) < DATE '{CURRENT_PROVEN_RESEARCH_START_DATE}'
              AND (NSE_BROAD_LIQUID_PIT_V1_eligible OR top750_liquidity)
          ), master AS (
            SELECT m.*
            FROM read_parquet('{r}/security_master.parquet') m
            JOIN pre2013_required p USING (security_id)
          ), symbol_stats AS (
            SELECT symbol,
              COUNT(DISTINCT security_id) AS symbol_security_count,
              COUNT(DISTINCT isin) FILTER (WHERE isin IS NOT NULL) AS symbol_isin_count
            FROM master
            GROUP BY symbol
          ), isin_stats AS (
            SELECT isin,
              COUNT(DISTINCT security_id) AS isin_security_count,
              COUNT(DISTINCT symbol) AS isin_symbol_count
            FROM master
            WHERE isin IS NOT NULL
            GROUP BY isin
          ), daily_gaps AS (
            SELECT security_id,
              MAX(session_index - previous_session_index - 1) AS max_absent_official_sessions
            FROM (
              SELECT p.security_id,
                c.session_index,
                LAG(c.session_index) OVER (PARTITION BY p.security_id ORDER BY c.session_index) AS previous_session_index
              FROM read_parquet('{r}/daily_prices_raw.parquet') p
              JOIN read_parquet('{r}/trading_calendar.parquet') c
                ON CAST(c.date AS DATE) = CAST(p.date AS DATE)
              JOIN pre2013_required q USING (security_id)
              WHERE CAST(p.date AS DATE) < DATE '{CURRENT_PROVEN_RESEARCH_START_DATE}'
            )
            WHERE previous_session_index IS NOT NULL
            GROUP BY security_id
          ), episode_stats AS (
            SELECT security_id,
              COUNT(DISTINCT listing_episode_id) AS episode_count,
              COUNT(DISTINCT symbol) AS symbol_count,
              COUNT(DISTINCT isin) FILTER (WHERE isin IS NOT NULL) AS isin_count,
              COUNT(DISTINCT company_name) AS company_name_count,
              MIN(first_seen) AS first_seen,
              MAX(last_seen) AS last_seen,
              MAX(CASE WHEN listing_history_left_censored THEN 1 ELSE 0 END)::BOOLEAN AS has_left_censored_episode
            FROM master
            GROUP BY security_id
          )
          SELECT e.security_id,
            MIN(m.symbol) AS representative_symbol,
            MIN(m.company_name) AS representative_company,
            e.first_seen,
            e.last_seen,
            e.episode_count,
            e.symbol_count,
            e.isin_count,
            e.company_name_count,
            MAX(COALESCE(s.symbol_security_count, 0)) AS max_symbol_security_count,
            MAX(COALESCE(s.symbol_isin_count, 0)) AS max_symbol_isin_count,
            MAX(COALESCE(i.isin_security_count, 0)) AS max_isin_security_count,
            MAX(COALESCE(i.isin_symbol_count, 0)) AS max_isin_symbol_count,
            COALESCE(MAX(d.max_absent_official_sessions), 0) AS max_absent_official_sessions,
            e.has_left_censored_episode
          FROM episode_stats e
          JOIN master m USING (security_id)
          LEFT JOIN symbol_stats s ON s.symbol = m.symbol
          LEFT JOIN isin_stats i ON i.isin = m.isin
          LEFT JOIN daily_gaps d USING (security_id)
          GROUP BY e.security_id, e.first_seen, e.last_seen, e.episode_count, e.symbol_count,
                   e.isin_count, e.company_name_count, e.has_left_censored_episode
          ORDER BY max_symbol_security_count DESC, max_isin_symbol_count DESC,
                   max_absent_official_sessions DESC, e.episode_count DESC, e.security_id
        """).fetchall()
        candidate_values = ", ".join(f"(DATE '{candidate}')" for candidate in CANDIDATE_RESEARCH_START_DATES)
        pre2013_identity_promotion_rows = connection.execute(f"""
          WITH candidates(candidate_start) AS (
            VALUES {candidate_values}
          ), scoped_monthly AS (
            SELECT c.candidate_start,
              u.security_id,
              u.research_identity_quality,
              u.research_identity_ok,
              CAST(u.date AS DATE) AS date
            FROM candidates c
            LEFT JOIN read_parquet('{r}/research_universe_monthly.parquet') u
              ON CAST(u.date AS DATE) >= c.candidate_start
             AND CAST(u.date AS DATE) < DATE '{CURRENT_PROVEN_RESEARCH_START_DATE}'
             AND (u.NSE_BROAD_LIQUID_PIT_V1_eligible OR u.top750_liquidity)
          ), security_scope AS (
            SELECT candidate_start,
              security_id,
              MIN(date) AS first_month,
              MAX(date) AS last_month,
              MIN(CASE WHEN research_identity_ok THEN 1 ELSE 0 END)::BOOLEAN AS identity_ok,
              MIN(research_identity_quality) AS identity_quality
            FROM scoped_monthly
            WHERE security_id IS NOT NULL
            GROUP BY candidate_start, security_id
          )
          SELECT c.candidate_start,
            MIN(s.first_month) AS first_month,
            MAX(s.last_month) AS last_month,
            COUNT(DISTINCT s.security_id) AS required_securities,
            COUNT(DISTINCT s.security_id) FILTER (WHERE s.identity_quality = 'RECONSTRUCTED_TRADING_IDENTITY' AND s.identity_ok) AS reconstructed_trading_identity,
            COUNT(DISTINCT s.security_id) FILTER (WHERE s.identity_quality <> 'RECONSTRUCTED_TRADING_IDENTITY' AND s.identity_ok) AS other_accepted_research_identities,
            COUNT(DISTINCT s.security_id) FILTER (WHERE s.identity_ok IS DISTINCT FROM TRUE) AS identity_failures
          FROM candidates c
          LEFT JOIN security_scope s USING (candidate_start)
          GROUP BY c.candidate_start
          ORDER BY c.candidate_start DESC
        """).fetchall()
        pre2013_adjustment_candidate_rows = connection.execute(f"""
          WITH candidates(candidate_start) AS (
            VALUES {candidate_values}
          ), candidate_sessions AS (
            SELECT c.candidate_start,
              MIN(cal.session_index) AS decision_session_index
            FROM candidates c
            LEFT JOIN read_parquet('{r}/trading_calendar.parquet') cal
              ON CAST(cal.date AS DATE) >= c.candidate_start
            GROUP BY c.candidate_start
          ), scoped_required AS (
            SELECT DISTINCT c.candidate_start, u.security_id
            FROM candidates c
            JOIN read_parquet('{r}/research_universe_monthly.parquet') u
              ON CAST(u.date AS DATE) >= c.candidate_start
             AND CAST(u.date AS DATE) < DATE '{CURRENT_PROVEN_RESEARCH_START_DATE}'
             AND (u.NSE_BROAD_LIQUID_PIT_V1_eligible OR u.top750_liquidity)
          ), material_events AS (
            SELECT sr.candidate_start,
              ca.event_id,
              ca.security_id,
              CAST(ca.event_date AS DATE) AS event_date,
              ca.event_type,
              ca.price_factor,
              ca.share_factor,
              COALESCE(v.validation_status, 'NO_BOUNDARY_VALIDATION') AS validation_status,
              cal.session_index AS event_session_index,
              cs.decision_session_index,
              (
                SELECT MAX(CAST(p.date AS DATE))
                FROM read_parquet('{r}/daily_prices_adjusted.parquet') p
                WHERE p.security_id = ca.security_id
                  AND CAST(p.date AS DATE) < CAST(ca.event_date AS DATE)
              ) AS any_pre_adjusted_date,
              (
                SELECT MIN(CAST(p.date AS DATE))
                FROM read_parquet('{r}/daily_prices_adjusted.parquet') p
                WHERE p.security_id = ca.security_id
                  AND CAST(p.date AS DATE) >= CAST(ca.event_date AS DATE)
              ) AS any_post_adjusted_date
            FROM scoped_required sr
            JOIN read_parquet('{r}/corporate_actions.parquet') ca USING (security_id)
            JOIN candidate_sessions cs USING (candidate_start)
            LEFT JOIN read_parquet('{r}/corporate_action_boundary_validation.parquet') v
              ON v.event_id = ca.event_id
            LEFT JOIN read_parquet('{r}/trading_calendar.parquet') cal
              ON CAST(cal.date AS DATE) = CAST(ca.event_date AS DATE)
            WHERE ca.event_type IN {MATERIAL_ACTIONS}
              AND CAST(ca.event_date AS DATE) < DATE '{CURRENT_PROVEN_RESEARCH_START_DATE}'
              AND (
                CAST(ca.event_date AS DATE) >= sr.candidate_start
                OR cal.session_index >= cs.decision_session_index - {max(FEATURE_READINESS_WINDOWS.values())}
              )
          )
          SELECT candidate_start,
            COUNT(DISTINCT event_id) AS material_events,
            COUNT(DISTINCT event_id) FILTER (WHERE price_factor IS NULL OR share_factor IS NULL) AS missing_factors,
            COUNT(DISTINCT event_id) FILTER (WHERE validation_status <> 'PASS') AS non_pass_boundaries,
            COUNT(DISTINCT event_id) FILTER (WHERE validation_status IN ('NO_PRE_EVENT_OBSERVATION', 'LEFT_CENSORED_BOUNDARY_VALIDATION')) AS left_censored_boundaries,
            COUNT(DISTINCT event_id) FILTER (
              WHERE validation_status <> 'PASS'
                AND event_session_index >= decision_session_index - {max(FEATURE_READINESS_WINDOWS.values())}
            ) AS possible_signal_window_non_pass_boundaries,
            COUNT(DISTINCT event_id) FILTER (
              WHERE validation_status <> 'PASS'
                AND event_session_index >= decision_session_index - {max(FEATURE_READINESS_WINDOWS.values())}
                AND any_pre_adjusted_date IS NULL
                AND any_post_adjusted_date IS NOT NULL
            ) AS left_censored_non_pass_no_crossing_boundaries,
            COUNT(DISTINCT event_id) FILTER (
              WHERE validation_status <> 'PASS'
                AND event_session_index >= decision_session_index - {max(FEATURE_READINESS_WINDOWS.values())}
                AND any_pre_adjusted_date IS NOT NULL
                AND any_post_adjusted_date IS NOT NULL
            ) AS contaminating_signal_window_non_pass_boundaries
          FROM material_events
          GROUP BY candidate_start
          ORDER BY candidate_start DESC
        """).fetchall()
        pre2013_adjusted_outlier_rows = connection.execute(f"""
          WITH required_pre2013 AS (
            SELECT DISTINCT security_id
            FROM read_parquet('{r}/research_universe_monthly.parquet')
            WHERE CAST(date AS DATE) < DATE '{CURRENT_PROVEN_RESEARCH_START_DATE}'
              AND (NSE_BROAD_LIQUID_PIT_V1_eligible OR top750_liquidity)
          ), adjusted_returns AS (
            SELECT p.security_id,
              CAST(p.date AS DATE) AS date,
              p.price_return_adjusted_close,
              LAG(p.price_return_adjusted_close) OVER (PARTITION BY p.security_id ORDER BY CAST(p.date AS DATE)) AS previous_adjusted_close
            FROM read_parquet('{r}/daily_prices_adjusted.parquet') p
            JOIN required_pre2013 q USING (security_id)
            WHERE CAST(p.date AS DATE) < DATE '{CURRENT_PROVEN_RESEARCH_START_DATE}'
          ), returns AS (
            SELECT security_id,
              date,
              CASE WHEN previous_adjusted_close IS NOT NULL AND previous_adjusted_close <> 0
                THEN price_return_adjusted_close / previous_adjusted_close - 1
              END AS adjusted_return
            FROM adjusted_returns
          ), event_dates AS (
            SELECT DISTINCT security_id, CAST(event_date AS DATE) AS event_date
            FROM read_parquet('{r}/corporate_actions.parquet')
            WHERE event_type IN {MATERIAL_ACTIONS}
          )
          SELECT r.security_id,
            MIN(m.symbol) AS symbol,
            MIN(m.company_name) AS company_name,
            r.date,
            r.adjusted_return,
            CASE
              WHEN e.event_date IS NOT NULL THEN 'CORPORATE_ACTION_ADJACENT'
              WHEN ABS(r.adjusted_return) > 0.60 THEN 'EXTREME_RETURN_GT_60_PCT_REVIEW'
              ELSE 'EXTREME_RETURN_GT_40_PCT_REVIEW'
            END AS classification
          FROM returns r
          JOIN read_parquet('{r}/security_master.parquet') m USING (security_id)
          LEFT JOIN event_dates e
            ON e.security_id = r.security_id
           AND e.event_date BETWEEN r.date - INTERVAL 1 DAY AND r.date + INTERVAL 1 DAY
          WHERE ABS(r.adjusted_return) > 0.40
          GROUP BY r.security_id, r.date, r.adjusted_return, e.event_date
          ORDER BY ABS(r.adjusted_return) DESC, r.date, r.security_id
          LIMIT 100
        """).fetchall()
        product_marker_sql = """
          regexp_matches(UPPER(COALESCE(symbol_at_date, '') || ' ' || COALESCE(company_name, '')),
            '(ETF|BEES|LIQUID|GILT|GOLD|SILVER|FUND|MUTUAL|NIFTY|SENSEX|BANKBEES|JUNIORBEES|PSUBNKBEES|SHARIAHBEES|PREF|PREFERENCE|WARRANT|RIGHTS|REIT|INVIT)')
        """
        exact_product_symbol_sql = """
          UPPER(COALESCE(symbol_at_date, '')) IN (
            'AXISGOLD', 'GOLDSHARE', 'IDBIGOLD', 'IIFLNIFTY',
            'KOTAKGOLD', 'MGOLD', 'QGOLDHALF', 'RELGOLD'
          )
        """
        pre2013_instrument_candidate_rows = connection.execute(f"""
          WITH candidates(candidate_start) AS (
            VALUES {candidate_values}
          ), scoped AS (
            SELECT c.candidate_start,
              u.security_id,
              u.instrument_type,
              u.instrument_type_quality,
              {product_marker_sql} AS product_like_marker,
              {exact_product_symbol_sql} AS known_product_symbol
            FROM candidates c
            LEFT JOIN read_parquet('{r}/research_universe_monthly.parquet') u
              ON CAST(u.date AS DATE) >= c.candidate_start
             AND CAST(u.date AS DATE) < DATE '{CURRENT_PROVEN_RESEARCH_START_DATE}'
             AND (u.NSE_BROAD_LIQUID_PIT_V1_eligible OR u.top750_liquidity)
          ), security_scope AS (
            SELECT candidate_start,
              security_id,
              MIN(instrument_type) AS instrument_type,
              MIN(instrument_type_quality) AS instrument_type_quality,
              MAX(CASE WHEN product_like_marker THEN 1 ELSE 0 END)::BOOLEAN AS product_like_marker,
              MAX(CASE WHEN known_product_symbol THEN 1 ELSE 0 END)::BOOLEAN AS known_product_symbol
            FROM scoped
            WHERE security_id IS NOT NULL
            GROUP BY candidate_start, security_id
          )
          SELECT c.candidate_start,
            COUNT(DISTINCT s.security_id) AS required_securities,
            COUNT(DISTINCT s.security_id) FILTER (WHERE s.instrument_type <> 'ORDINARY_EQUITY') AS non_ordinary,
            COUNT(DISTINCT s.security_id) FILTER (WHERE s.instrument_type_quality IS NULL OR s.instrument_type_quality = 'UNRESOLVED') AS ambiguous_quality,
            COUNT(DISTINCT s.security_id) FILTER (WHERE s.known_product_symbol) AS known_product_symbols,
            COUNT(DISTINCT s.security_id) FILTER (WHERE s.instrument_type = 'ORDINARY_EQUITY' AND s.product_like_marker AND NOT s.known_product_symbol) AS product_like_ordinary_review
          FROM candidates c
          LEFT JOIN security_scope s USING (candidate_start)
          GROUP BY c.candidate_start
          ORDER BY c.candidate_start DESC
        """).fetchall()
        pre2013_instrument_review_rows = connection.execute(f"""
          WITH scoped AS (
            SELECT security_id,
              MIN(symbol_at_date) AS symbol,
              MIN(company_name) AS company_name,
              MIN(CAST(date AS DATE)) AS first_month,
              MAX(CAST(date AS DATE)) AS last_month,
              MIN(instrument_type) AS instrument_type,
              MIN(instrument_type_quality) AS instrument_type_quality,
              MIN(liquidity_rank_126) AS best_rank_126,
              COUNT(DISTINCT date) AS research_months,
              MAX(CASE WHEN {product_marker_sql} THEN 1 ELSE 0 END)::BOOLEAN AS product_like_marker,
              MAX(CASE WHEN {exact_product_symbol_sql} THEN 1 ELSE 0 END)::BOOLEAN AS known_product_symbol
            FROM read_parquet('{r}/research_universe_monthly.parquet')
            WHERE CAST(date AS DATE) < DATE '{CURRENT_PROVEN_RESEARCH_START_DATE}'
              AND (NSE_BROAD_LIQUID_PIT_V1_eligible OR top750_liquidity)
            GROUP BY security_id
          )
          SELECT security_id,
            symbol,
            company_name,
            first_month,
            last_month,
            instrument_type,
            instrument_type_quality,
            best_rank_126,
            research_months,
            product_like_marker,
            known_product_symbol
          FROM scoped
          WHERE instrument_type <> 'ORDINARY_EQUITY'
             OR instrument_type_quality IS NULL
             OR instrument_type_quality = 'UNRESOLVED'
             OR product_like_marker
             OR known_product_symbol
          ORDER BY
            CASE
              WHEN instrument_type <> 'ORDINARY_EQUITY' THEN 0
              WHEN instrument_type_quality IS NULL OR instrument_type_quality = 'UNRESOLVED' THEN 1
              WHEN known_product_symbol THEN 2
              WHEN product_like_marker THEN 3
              ELSE 3
            END,
            best_rank_126 NULLS LAST,
            security_id
          LIMIT 200
        """).fetchall()
        pre2013_terminal_priority_rows = connection.execute(f"""
          WITH required_monthly AS (
            SELECT security_id,
              MIN(CAST(date AS DATE)) AS first_required_month,
              MAX(CAST(date AS DATE)) AS last_required_month,
              MIN(liquidity_rank_126) AS best_rank_126,
              COUNT(DISTINCT date) AS research_months,
              MAX(CASE WHEN NSE_BROAD_LIQUID_PIT_V1_eligible THEN 1 ELSE 0 END)::BOOLEAN AS enters_liquid_v1,
              MAX(CASE WHEN top750_liquidity THEN 1 ELSE 0 END)::BOOLEAN AS enters_top750
            FROM read_parquet('{r}/research_universe_monthly.parquet')
            WHERE CAST(date AS DATE) < DATE '{CURRENT_PROVEN_RESEARCH_START_DATE}'
              AND (NSE_BROAD_LIQUID_PIT_V1_eligible OR top750_liquidity)
            GROUP BY security_id
          ), last_seen AS (
            SELECT security_id,
              MAX(CAST(date AS DATE)) AS last_observed_date
            FROM read_parquet('{r}/daily_prices_raw.parquet')
            GROUP BY security_id
          ), names AS (
            SELECT security_id,
              MIN(symbol) AS symbol,
              MIN(company_name) AS company_name
            FROM read_parquet('{r}/security_master.parquet')
            GROUP BY security_id
          ), terminal AS (
            SELECT security_id,
              MIN(CAST(terminal_event_date AS DATE)) AS first_terminal_event_date,
              STRING_AGG(DISTINCT terminal_event_type, ', ') AS terminal_event_types,
              STRING_AGG(DISTINCT terminal_value_quality, ', ') AS terminal_value_quality
            FROM read_parquet('{r}/terminal_events.parquet')
            GROUP BY security_id
          )
          SELECT rm.security_id,
            n.symbol,
            n.company_name,
            rm.first_required_month,
            rm.last_required_month,
            rm.best_rank_126,
            rm.research_months,
            rm.enters_liquid_v1,
            rm.enters_top750,
            ls.last_observed_date,
            COALESCE(t.first_terminal_event_date, ls.last_observed_date) AS terminal_reference_date,
            COALESCE(t.terminal_event_types, 'UNKNOWN_TERMINAL_EVENT') AS terminal_event_types,
            COALESCE(t.terminal_value_quality, 'UNKNOWN') AS terminal_value_quality
          FROM required_monthly rm
          JOIN last_seen ls USING (security_id)
          JOIN names n USING (security_id)
          LEFT JOIN terminal t USING (security_id)
          WHERE ls.last_observed_date < DATE '{coverage[1]}'
          ORDER BY rm.best_rank_126 NULLS LAST, rm.research_months DESC, rm.security_id
          LIMIT 200
        """).fetchall()
        pre2013_survivorship_year_rows = connection.execute(f"""
          WITH required_by_year AS (
            SELECT EXTRACT(YEAR FROM CAST(date AS DATE))::INTEGER AS year,
              security_id,
              MAX(CASE WHEN NSE_BROAD_LIQUID_PIT_V1_eligible THEN 1 ELSE 0 END)::BOOLEAN AS enters_liquid_v1,
              MAX(CASE WHEN top750_liquidity THEN 1 ELSE 0 END)::BOOLEAN AS enters_top750
            FROM read_parquet('{r}/research_universe_monthly.parquet')
            WHERE CAST(date AS DATE) < DATE '{CURRENT_PROVEN_RESEARCH_START_DATE}'
              AND (NSE_BROAD_LIQUID_PIT_V1_eligible OR top750_liquidity)
            GROUP BY 1, 2
          ), last_seen AS (
            SELECT security_id,
              MAX(CAST(date AS DATE)) AS last_observed_date
            FROM read_parquet('{r}/daily_prices_raw.parquet')
            GROUP BY security_id
          )
          SELECT r.year,
            COUNT(DISTINCT r.security_id) AS required_securities,
            COUNT(DISTINCT r.security_id) FILTER (WHERE l.last_observed_date = DATE '{coverage[1]}') AS current_survivors,
            COUNT(DISTINCT r.security_id) FILTER (WHERE l.last_observed_date < DATE '{coverage[1]}') AS non_survivors,
            COUNT(DISTINCT r.security_id) FILTER (WHERE r.enters_liquid_v1) AS liquid_v1_securities,
            COUNT(DISTINCT r.security_id) FILTER (WHERE r.enters_top750) AS top750_securities
          FROM required_by_year r
          JOIN last_seen l USING (security_id)
          GROUP BY r.year
          ORDER BY r.year
        """).fetchall()
        pre2013_survivorship_example_rows = connection.execute(f"""
          WITH required_monthly AS (
            SELECT security_id,
              MIN(CAST(date AS DATE)) AS first_required_month,
              MAX(CAST(date AS DATE)) AS last_required_month,
              MIN(liquidity_rank_126) AS best_rank_126,
              MAX(CASE WHEN NSE_BROAD_LIQUID_PIT_V1_eligible THEN 1 ELSE 0 END)::BOOLEAN AS enters_liquid_v1,
              MAX(CASE WHEN top750_liquidity THEN 1 ELSE 0 END)::BOOLEAN AS enters_top750
            FROM read_parquet('{r}/research_universe_monthly.parquet')
            WHERE CAST(date AS DATE) < DATE '{CURRENT_PROVEN_RESEARCH_START_DATE}'
              AND (NSE_BROAD_LIQUID_PIT_V1_eligible OR top750_liquidity)
            GROUP BY security_id
          ), last_seen AS (
            SELECT security_id,
              MAX(CAST(date AS DATE)) AS last_observed_date
            FROM read_parquet('{r}/daily_prices_raw.parquet')
            GROUP BY security_id
          ), names AS (
            SELECT security_id,
              MIN(symbol) AS symbol,
              MIN(company_name) AS company_name
            FROM read_parquet('{r}/security_master.parquet')
            GROUP BY security_id
          ), terminal AS (
            SELECT security_id,
              STRING_AGG(DISTINCT terminal_event_type, ', ') AS terminal_event_types
            FROM read_parquet('{r}/terminal_events.parquet')
            GROUP BY security_id
          )
          SELECT rm.security_id,
            n.symbol,
            n.company_name,
            rm.first_required_month,
            rm.last_required_month,
            rm.best_rank_126,
            rm.enters_liquid_v1,
            rm.enters_top750,
            ls.last_observed_date,
            COALESCE(t.terminal_event_types, 'UNKNOWN_TERMINAL_EVENT') AS terminal_event_types
          FROM required_monthly rm
          JOIN last_seen ls USING (security_id)
          JOIN names n USING (security_id)
          LEFT JOIN terminal t USING (security_id)
          WHERE ls.last_observed_date < DATE '{coverage[1]}'
          ORDER BY rm.best_rank_126 NULLS LAST, rm.security_id
          LIMIT 25
        """).fetchall()
        pre2013_historical_count_rows = connection.execute(f"""
          SELECT EXTRACT(YEAR FROM CAST(date AS DATE))::INTEGER AS year,
            COUNT(DISTINCT security_id) AS active_ordinary,
            COUNT(DISTINCT security_id) FILTER (WHERE history_sessions >= {LIQUID_V1_DEFINITION["listing_age_sessions_min"]}) AS fully_seasoned_observed_history,
            COUNT(DISTINCT security_id) FILTER (WHERE model_handoff_history_ready_300) AS model_handoff_ready_300,
            COUNT(DISTINCT security_id) FILTER (WHERE NSE_BROAD_LIQUID_PIT_V1_eligible) AS liquid_v1,
            COUNT(DISTINCT security_id) FILTER (WHERE top500_liquidity) AS top500,
            COUNT(DISTINCT security_id) FILTER (WHERE top750_liquidity) AS top750,
            COUNT(DISTINCT security_id) FILTER (WHERE top1000_liquidity) AS top1000,
            COUNT(DISTINCT security_id) FILTER (WHERE NSE_BROAD_LIQUID_PIT_V1_eligible OR top750_liquidity) AS required_scope,
            COUNT(DISTINCT security_id) FILTER (WHERE signal_history_ready_252) AS signal_ready_252,
            COUNT(DISTINCT security_id) FILTER (WHERE signal_history_ready_273) AS signal_ready_273
          FROM read_parquet('{r}/research_universe_monthly.parquet')
          WHERE CAST(date AS DATE) < DATE '{CURRENT_PROVEN_RESEARCH_START_DATE}'
          GROUP BY 1
          ORDER BY 1
        """).fetchall()
        disappeared_rows = connection.execute(f"""
          WITH eligible AS (
            SELECT security_id, MAX(CAST(date AS DATE)) AS last_eligible_date
            FROM read_parquet('{r}/research_universe_monthly.parquet')
            WHERE NSE_BROAD_LIQUID_PIT_V1_eligible
            GROUP BY security_id
          ), last_seen AS (
            SELECT security_id, MAX(CAST(date AS DATE)) AS last_observed_date
            FROM read_parquet('{r}/daily_prices_raw.parquet')
            GROUP BY security_id
          ), symbols AS (
            SELECT security_id, MIN(symbol) AS symbol
            FROM read_parquet('{r}/security_master.parquet') GROUP BY security_id
          ), terminal AS (
            SELECT security_id, STRING_AGG(DISTINCT terminal_event_type, ', ') AS terminal_types
            FROM read_parquet('{r}/terminal_events.parquet') GROUP BY security_id
          )
          SELECT e.security_id, s.symbol, e.last_eligible_date, l.last_observed_date,
                 COALESCE(t.terminal_types, 'UNKNOWN_TERMINAL_EVENT')
          FROM eligible e JOIN last_seen l USING (security_id) JOIN symbols s USING (security_id)
          LEFT JOIN terminal t USING (security_id)
          WHERE l.last_observed_date < DATE '{coverage[1]}'
          ORDER BY e.last_eligible_date DESC, e.security_id
          LIMIT 25
        """).fetchall()
        disappeared_count = scalar(connection, f"""
          SELECT COUNT(*) FROM (
            SELECT security_id, MAX(CAST(date AS DATE)) AS last_observed
            FROM read_parquet('{r}/daily_prices_raw.parquet') GROUP BY security_id
          ) WHERE last_observed < DATE '{coverage[1]}'
        """)
        current_survivor_eligible = scalar(connection, f"""
          SELECT COUNT(DISTINCT u.security_id)
          FROM read_parquet('{r}/research_universe_monthly.parquet') u
          JOIN (SELECT security_id, MAX(CAST(date AS DATE)) AS last_seen FROM read_parquet('{r}/daily_prices_raw.parquet') GROUP BY security_id) l USING (security_id)
          WHERE u.NSE_BROAD_LIQUID_PIT_V1_eligible AND l.last_seen = DATE '{coverage[1]}'
        """)
        historical_eligible = scalar(connection, f"SELECT COUNT(DISTINCT security_id) FROM read_parquet('{r}/research_universe_monthly.parquet') WHERE NSE_BROAD_LIQUID_PIT_V1_eligible")
        required_scope_failure_count = scalar(connection, f"""
          SELECT COUNT(DISTINCT security_id)
          FROM read_parquet('{r}/research_universe_monthly.parquet')
          WHERE CAST(date AS DATE) >= DATE '{research_start}'
            AND (NSE_BROAD_LIQUID_PIT_V1_eligible OR top750_liquidity)
            AND NOT research_identity_ok
        """)
        yearly_required_rows = connection.execute(f"""
          SELECT EXTRACT(YEAR FROM date)::INTEGER AS year,
            COUNT(DISTINCT security_id) FILTER (WHERE top750_liquidity OR NSE_BROAD_LIQUID_PIT_V1_eligible) AS required_count,
            COUNT(DISTINCT security_id) FILTER (WHERE (top750_liquidity OR NSE_BROAD_LIQUID_PIT_V1_eligible) AND research_identity_ok) AS identity_passing,
            COUNT(DISTINCT security_id) FILTER (WHERE (top750_liquidity OR NSE_BROAD_LIQUID_PIT_V1_eligible) AND NOT research_identity_ok) AS identity_failures,
            COUNT(DISTINCT security_id) FILTER (WHERE (top750_liquidity OR NSE_BROAD_LIQUID_PIT_V1_eligible) AND NOT price_adjustment_ok) AS price_action_failures,
            COUNT(DISTINCT security_id) FILTER (WHERE (top750_liquidity OR NSE_BROAD_LIQUID_PIT_V1_eligible) AND (instrument_type <> 'ORDINARY_EQUITY' OR instrument_type_quality IS NULL OR instrument_type_quality = 'UNRESOLVED')) AS instrument_classification_failures,
            COUNT(DISTINCT security_id) FILTER (WHERE (top750_liquidity OR NSE_BROAD_LIQUID_PIT_V1_eligible) AND status_quality = 'UNKNOWN_STATUS') AS unknown_status_exclusions
          FROM read_parquet('{r}/research_universe_monthly.parquet')
          GROUP BY 1 ORDER BY 1
        """).fetchall()
        material_action_year_rows = connection.execute(f"""
          WITH required_by_year AS (
            SELECT DISTINCT
              EXTRACT(YEAR FROM CAST(date AS DATE))::INTEGER AS year,
              security_id
            FROM read_parquet('{r}/research_universe_monthly.parquet')
            WHERE top750_liquidity OR NSE_BROAD_LIQUID_PIT_V1_eligible
          )
          SELECT EXTRACT(YEAR FROM CAST(ca.event_date AS DATE))::INTEGER AS year,
            COUNT(*) FILTER (WHERE ca.price_factor IS NULL OR ca.share_factor IS NULL) AS missing_factors
          FROM read_parquet('{r}/corporate_actions.parquet') ca
          JOIN required_by_year q
            ON q.security_id = ca.security_id
           AND q.year = EXTRACT(YEAR FROM CAST(ca.event_date AS DATE))::INTEGER
          WHERE ca.event_type IN {MATERIAL_ACTIONS}
          GROUP BY 1 ORDER BY 1
        """).fetchall()
        boundary_warning_year_rows = connection.execute(f"""
          WITH required_by_year AS (
            SELECT DISTINCT
              EXTRACT(YEAR FROM CAST(date AS DATE))::INTEGER AS year,
              security_id
            FROM read_parquet('{r}/research_universe_monthly.parquet')
            WHERE top750_liquidity OR NSE_BROAD_LIQUID_PIT_V1_eligible
          )
          SELECT EXTRACT(YEAR FROM CAST(v.ex_date AS DATE))::INTEGER AS year,
            COUNT(DISTINCT v.event_id) FILTER (WHERE v.validation_status IN (
              'WARNING_LARGE_BOUNDARY_MOVE',
              'INVALID_PRE_EVENT_PRICE',
              'NO_BOUNDARY_OBSERVATIONS',
              'NO_LOCAL_BOUNDARY_OBSERVATION',
              'NO_PRE_EVENT_OBSERVATION',
              'NO_POST_EVENT_OBSERVATION',
              'LEFT_CENSORED_BOUNDARY_VALIDATION'
            )) AS boundary_warnings
          FROM read_parquet('{r}/corporate_action_boundary_validation.parquet') v
          JOIN required_by_year q
            ON q.security_id = v.security_id
           AND q.year = EXTRACT(YEAR FROM CAST(v.ex_date AS DATE))::INTEGER
          GROUP BY 1 ORDER BY 1
        """).fetchall()
        terminal_sensitivity_count = scalar(connection, f"""
          WITH required_scope AS (
            SELECT DISTINCT security_id
            FROM read_parquet('{r}/research_universe_monthly.parquet')
            WHERE top750_liquidity OR NSE_BROAD_LIQUID_PIT_V1_eligible
          )
          SELECT COUNT(DISTINCT q.security_id)
          FROM required_scope q
          JOIN read_parquet('{r}/terminal_events.parquet') t USING (security_id)
          WHERE t.terminal_value IS NULL OR t.terminal_value_quality IN ('UNKNOWN', 'UNRESOLVED')
        """)
        terminal_sensitivity_year_rows = connection.execute(f"""
          WITH required_by_year AS (
            SELECT DISTINCT
              EXTRACT(YEAR FROM CAST(date AS DATE))::INTEGER AS year,
              security_id
            FROM read_parquet('{r}/research_universe_monthly.parquet')
            WHERE top750_liquidity OR NSE_BROAD_LIQUID_PIT_V1_eligible
          )
          SELECT q.year, COUNT(DISTINCT q.security_id) AS terminal_sensitivity_count
          FROM required_by_year q
          JOIN read_parquet('{r}/terminal_events.parquet') t USING (security_id)
          WHERE t.terminal_value IS NULL OR t.terminal_value_quality IN ('UNKNOWN', 'UNRESOLVED')
          GROUP BY q.year
          ORDER BY q.year
        """).fetchall()
        pre2013_monthly_summary = connection.execute(f"""
          SELECT COUNT(*) AS rows,
            COUNT(DISTINCT security_id) AS securities,
            COUNT(DISTINCT security_id) FILTER (WHERE NSE_BROAD_LIQUID_PIT_V1_eligible OR top750_liquidity) AS required_securities,
            COUNT(DISTINCT security_id) FILTER (WHERE (NSE_BROAD_LIQUID_PIT_V1_eligible OR top750_liquidity) AND isin IS NULL) AS missing_isin_required,
            COUNT(DISTINCT security_id) FILTER (WHERE (NSE_BROAD_LIQUID_PIT_V1_eligible OR top750_liquidity) AND NOT research_identity_ok) AS identity_failures,
            MAX(absent_observation_days_60) AS max_absent_days_60,
            COUNT(*) FILTER (WHERE NOT signal_history_ready_273) AS signal_not_ready_273_rows
          FROM read_parquet('{r}/research_universe_monthly.parquet')
          WHERE CAST(date AS DATE) < DATE '{CURRENT_PROVEN_RESEARCH_START_DATE}'
        """).fetchone()
        left_censored_security_count = scalar(connection, f"""
          WITH first_source AS (
            SELECT MIN(CAST(date AS DATE)) AS first_date FROM read_parquet('{r}/daily_prices_raw.parquet')
          ), first_seen AS (
            SELECT security_id, MIN(CAST(date AS DATE)) AS first_seen
            FROM read_parquet('{r}/daily_prices_raw.parquet')
            GROUP BY security_id
          )
          SELECT COUNT(*) FROM first_seen, first_source
          WHERE first_seen = first_date
        """)
        left_boundary_events = scalar(connection, f"""
          SELECT COUNT(DISTINCT event_id)
          FROM read_parquet('{r}/corporate_action_boundary_validation.parquet')
          WHERE validation_status IN ('NO_PRE_EVENT_OBSERVATION', 'LEFT_CENSORED_BOUNDARY_VALIDATION')
        """)
    finally:
        connection.close()

    missing_factor_count = sum(int(row[2]) for row in event_rows)
    git_sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    validation_path = reports / f"research_invariant_validation_{release.name}.json"
    candidate_promotion_audit_path = reports / f"candidate_promotion_audit_{release.name}.json"
    test_result_path = reports / f"test_results_{release.name}.xml"
    ci_status_path = reports / f"ci_status_{release.name}.json"
    partition_manifest_path = release / PARTITIONED_ARTIFACTS_MANIFEST
    validation_ok = validation_passed(validation_path)
    test_ok = junit_passed(test_result_path)
    ci_ok = ci_passed(ci_status_path, git_sha=git_sha)
    hard_evidence_gate_pass = int(required_scope_failure_count) == 0 and missing_factor_count == 0 and int(status_overlap) == 0

    year_map = {int(row[0]): row[1:] for row in yearly_required_rows}
    terminal_sensitivity_by_year = {int(row[0]): int(row[1]) for row in terminal_sensitivity_year_rows}
    year_text = ["| Year | Active ordinary | LIQUID_V1 | Top-750 | Required | Identity passing | Identity failures | Price-action failures | Unknown-status exclusions | Sparse names |", "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for y, a, l, t, _old_i, s in year_rows:
        required, passing, failures, price_failures, _instrument_failures, unknown_status = year_map[int(y)]
        year_text.append(f"| {int(y)} | {a} | {l} | {t} | {required} | {passing} | {failures} | {price_failures} | {unknown_status} | {s} |")
    write(reports / "research_universe_coverage.md", f"""# Research universe coverage

Profile: `NSE_BROAD_LIQUID_PIT_V1` / `LIQUID_V1`

Coverage: `{coverage[0]}` through `{coverage[1]}`.

Promoted-scope required research securities: `{promoted_required_count}` total (`{promoted_liquid_count}` LIQUID_V1 names and `{promoted_top750_count}` Top-750 names).

Candidate-plus-promoted support artifact securities: `{required_count}`.

{chr(10).join(year_text)}

The Top-750 set is a PIT liquidity diagnostic. It is not index membership.
""")
    sessions_by_year: dict[int, int] = {}
    fully_warmed_months_by_year: dict[int, int] = {}
    max_window_for_readiness = max(FEATURE_READINESS_WINDOWS.values())
    for index, point in enumerate(calendar_dates):
        year = int(point[:4])
        sessions_by_year[year] = sessions_by_year.get(year, 0) + 1
        if index >= max_window_for_readiness:
            fully_warmed_months_by_year[year] = fully_warmed_months_by_year.get(year, 0) + 1
    material_by_year = {int(year): int(missing) for year, missing in material_action_year_rows if year is not None}
    boundary_by_year = {int(year): int(warnings) for year, warnings in boundary_warning_year_rows if year is not None}
    readiness_years = sorted({int(row[0]) for row in year_rows} | set(sessions_by_year))
    readiness_text = [
        "# Research readiness by year",
        "",
        "This matrix is diagnostic. A `PASS` year still requires source integrity, PIT invariant, test, CI, and regression evidence before promotion.",
        "The readiness score is diagnostic only. Hard gates remain authoritative.",
        "",
        "| Year | Official sessions | Fully warmed sessions | Active ordinary | LIQUID_V1 | Top-750 | Required securities | Identity failures | Instrument failures | Missing material factors | Boundary warnings | Unknown-status exclusions | Terminal sensitivity count | Research invariant failures | Readiness score | Promotion status |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    year_rows_by_year = {int(row[0]): row for row in year_rows}
    for year in readiness_years:
        row = year_rows_by_year.get(year)
        active = liquid = top750 = 0
        if row:
            _year, active, liquid, top750, _old_i, _sparse = row
        required, _passing, identity_failures, price_failures, instrument_failures, unknown_status = year_map.get(year, (0, 0, 0, 0, 0, 0))
        missing_factors = material_by_year.get(year, 0)
        boundary_warnings = boundary_by_year.get(year, 0)
        terminal_sensitivity = terminal_sensitivity_by_year.get(year, 0)
        invariant_failures = identity_failures + price_failures + instrument_failures
        warmup_ready = fully_warmed_months_by_year.get(year, 0) > 0
        readiness_score = sum((
            sessions_by_year.get(year, 0) > 0,
            warmup_ready,
            identity_failures == 0,
            price_failures == 0 and missing_factors == 0,
            instrument_failures == 0,
        ))
        if sessions_by_year.get(year, 0) == 0:
            status = "FAIL"
        elif not warmup_ready:
            status = "FAIL"
        elif invariant_failures == 0 and missing_factors == 0:
            status = "PASS" if boundary_warnings == 0 else "PASS_WITH_SCOPED_LIMITATION"
        else:
            status = "FAIL"
        readiness_text.append(f"| {year} | {sessions_by_year.get(year, 0)} | {fully_warmed_months_by_year.get(year, 0)} | {active} | {liquid} | {top750} | {required} | {identity_failures} | {instrument_failures} | {missing_factors} | {boundary_warnings} | {unknown_status} | {terminal_sensitivity} | {invariant_failures} | {readiness_score}/5 | `{status}` |")
    readiness_text.extend([
        "",
        "Readiness score dimensions: source sessions present, full warmup present, identity gate clean, price-action gate clean, and instrument gate clean.",
        "A year cannot receive `PASS` unless at least one monthly decision session is fully warmed for the longest configured feature window.",
        "Boundary warnings are not automatically fatal when they are left-boundary limitations that cannot contaminate a promoted signal window.",
        "Promotion remains date-range scoped; this report does not force 2006-2026 to pass atomically.",
    ])
    write(reports / "research_readiness_by_year.md", "\n".join(readiness_text))
    pre2006_manifest_path = Path("data/raw/manifests/pre2006_source_reconnaissance.json")
    pre2006_rows = json.loads(pre2006_manifest_path.read_text(encoding="utf-8")) if pre2006_manifest_path.exists() else []
    pre2006_valid = sum(1 for row in pre2006_rows if row.get("download_status") in {"DOWNLOADED_VALID_ARCHIVE", "CACHED_VALID_ARCHIVE"})
    pre2013_rows, pre2013_securities, pre2013_required, pre2013_missing_isin, pre2013_identity_failures, pre2013_max_absent, pre2013_signal_not_ready = pre2013_monthly_summary
    bias_text = [
        "# Early-history bias risks",
        "",
        "This report is evidence-backed. `not available` means the current release artifacts do not yet contain that evidence.",
        "",
        "| Risk | Evidence | Current interpretation |",
        "|---|---|---|",
        f"| Left-censoring | `{left_censored_security_count}` securities first appear on the first observed source date `{observed_coverage.get('observed_start')}`. | These securities must not be treated as IPOs solely because source coverage starts there. |",
        f"| Pre-2006 market-data availability | `{pre2006_valid}` valid representative archives out of `{len(pre2006_rows)}` probed. | {'Pre-2006 warmup may be feasible, pending bulk integrity checks.' if pre2006_valid else 'Pre-2006 warmup is not established by current evidence.'} |",
        f"| Missing ISIN in early required scope | `{pre2013_missing_isin}` pre-2013 required securities lack ISIN in monthly snapshots. | Missing ISIN can still allow `RECONSTRUCTED_TRADING_IDENTITY`, but ticker reuse and continuity checks must pass. |",
        f"| Early identity failures | `{pre2013_identity_failures}` pre-2013 required securities fail research identity in monthly snapshots. | Any promoted interval must reduce required-scope identity failures to zero. |",
        f"| Early liquidity sparsity | Maximum pre-2013 `absent_observation_days_60`: `{pre2013_max_absent}`. | Sparse rows are counted through official-session windows, not ignored. |",
        f"| Signal warmup | `{pre2013_signal_not_ready}` pre-2013 monthly rows are not ready for 273-session momentum-style history. | Universe eligibility is separate from model/signal readiness. |",
        f"| Left-boundary price-action validation | `{left_boundary_events}` material boundary validations lack pre-event observations or are left-censored. | These are not PASS; they require contamination analysis before promotion. |",
        f"| Early monthly artifact coverage | `{pre2013_rows}` rows, `{pre2013_securities}` securities, `{pre2013_required}` required-scope securities before `{CURRENT_PROVEN_RESEARCH_START_DATE}`. | Zero values mean early candidate snapshots have not yet been materialized into this release. |",
        "| Market-cap and sector history | not available in release artifacts | These must not be backfilled from current classifications. |",
    ]
    bias_text.extend([
        "",
        "This report does not promote any early interval.",
        "Promotion still requires source integrity, warmup readiness, session liquidity, identity, instrument, material price-action, PIT invariant, CI, and test gates.",
    ])
    write(reports / "early_history_bias_risks.md", "\n".join(bias_text))
    identity_text = ["# Research identity promotion", "", f"Promoted research start: `{research_start}`.", f"Promoted-scope required research securities: `{promoted_required_count}`.", f"Candidate-plus-promoted support artifact securities: `{required_count}`.", f"Identity failures in the promoted required scope: `{required_scope_failure_count}`.", "", "| Research identity quality | Securities |", "|---|---:|"]
    identity_text.extend(f"| `{quality_name}` | {number} |" for quality_name, number in identity_rows)
    identity_text.extend(["", "A `RECONSTRUCTED_TRADING_IDENTITY` is accepted when dated master rows resolve to one listing episode, one series, and no conflicting ISIN evidence. Multiple rows can represent symbol or name history within that episode.", f"Promotion gate: `{'PASS' if int(required_scope_failure_count) == 0 else 'FAIL'}`."])
    write(reports / "research_identity_promotion.md", "\n".join(identity_text))
    event_text = ["# Research universe corporate-action audit", "", "Material price actions are `SPLIT`, `REVERSE_SPLIT`, and `BONUS`.", "", "| Event type | Events | Missing factors |", "|---|---:|---:|"]
    event_text.extend(f"| `{kind}` | {events} | {missing} |" for kind, events, missing in event_rows)
    event_text.extend(["", f"Material events with missing price/share factors in the promoted required scope: `{missing_factor_count}`.", f"Unresolved material boundary events in the promoted required scope: `{unresolved_boundary_count}`.", f"Promotion gate: `{'PASS' if missing_factor_count == 0 and int(unresolved_boundary_count) == 0 else 'FAIL'}`.", "", "## Boundary validation in the promoted required scope", "", "| Boundary status | Distinct events |", "|---|---:|"])
    event_text.extend(f"| `{status}` | {number} |" for status, number in boundary_rows)
    event_text.extend(["", "## Material event details", "", "| Security | Symbol | Event date | Type | Price factor | Share factor | Pre close | Post close | Raw boundary return | Adjusted boundary return | Holder value ratio | Validation |", "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|"])
    event_text.extend(f"| `{sid}` | `{symbol}` | `{event_date}` | `{event_type}` | {price_factor} | {share_factor} | {pre_close} | {post_close} | {raw_return} | {adjusted_return} | {holder_ratio} | `{status}` |" for sid, symbol, event_date, event_type, price_factor, share_factor, pre_close, post_close, raw_return, adjusted_return, holder_ratio, status in event_detail_rows)
    event_text.extend(["", "`NO_PRE_EVENT_OBSERVATION` and `NO_POST_EVENT_OBSERVATION` identify listing-start or terminal-history edges. `NO_LOCAL_BOUNDARY_OBSERVATION` means the nearest price is more than five official sessions from the event. These cases do not create a false return and do not change the official factor or raw price. A local two-sided boundary is required before continuity is assessed.", "", "Rows remain traceable to `corporate_actions.parquet`; this report does not alter raw nominal prices."])
    write(reports / "research_universe_corporate_action_audit.md", "\n".join(event_text))
    adjustment_text = ["# Research price-adjustment promotion", "", "The recommended signal series is the price-return adjusted close. Raw nominal prices remain the execution series.", "", "| Adjustment quality | Rows |", "|---|---:|"]
    adjustment_text.extend(f"| `{kind}` | {number} |" for kind, number in adjustment_rows)
    adjustment_text.extend(["", f"Promoted-scope material-event factor gate: `{'PASS' if missing_factor_count == 0 else 'FAIL'}`.", "Total-return adjustment is separate and remains partial unless its own quality says otherwise."])
    write(reports / "research_price_adjustment_promotion.md", "\n".join(adjustment_text))
    write(reports / "session_correct_liquidity_audit.md", f"""# Session-correct liquidity audit

Liquidity windows use official NSE session positions from `trading_calendar.parquet`.

- Window definitions: 20, 60, 126, and 252 official sessions.
- Positive-volume days count only observed rows with volume greater than zero.
- Zero-volume days count observed rows with zero or null volume.
- Absent-observation days count official sessions with no security row.
- Maximum absent-observation count in the monthly research artifact: `{max_absent}`.
- Ranking metric: trailing 126-session median traded value.

The feature artifact contains `liquidity_window_definition = OFFICIAL_NSE_SESSION_WINDOW`.
Weekend and holiday dates are not part of any window.
""")
    max_window = max(FEATURE_READINESS_WINDOWS.values())
    warmup_months = []
    for index, point in enumerate(calendar_dates):
        if point < str(observed_coverage.get("observed_start", "")):
            continue
        month = point[:7]
        if warmup_months and warmup_months[-1][0] == month:
            warmup_months[-1] = (month, point, index)
        else:
            warmup_months.append((month, point, index))
    warmup_text = ["# Research warmup coverage", "", "Readiness is measured from official NSE market sessions available before the candidate decision date.", "", f"Longest configured warmup: `{max_window}` prior official sessions.", "", "| Month | Decision session | Prior official sessions | 20 ready | 60 ready | 126 ready | 252 ready | 272 ready | 273 ready | Full handoff ready |", "|---|---|---:|---|---|---|---|---|---|---|"]
    first_full_ready = None
    for _month, point, prior_sessions in warmup_months:
        ready = {name: prior_sessions >= window for name, window in FEATURE_READINESS_WINDOWS.items()}
        full_ready = prior_sessions >= max_window
        if full_ready and first_full_ready is None:
            first_full_ready = point
        warmup_text.append(
            f"| {_month} | {point} | {prior_sessions} | "
            f"{'Y' if ready['liquidity_20'] else 'N'} | "
            f"{'Y' if ready['liquidity_60'] else 'N'} | "
            f"{'Y' if ready['liquidity_rank_126'] else 'N'} | "
            f"{'Y' if ready['standard_research_252'] else 'N'} | "
            f"{'Y' if ready['liquid_v1_listing_age'] else 'N'} | "
            f"{'Y' if ready['momentum_12_1'] else 'N'} | "
            f"{'Y' if full_ready else 'N'} |"
        )
    warmup_text.extend(["", f"First fully warmed monthly decision session: `{first_full_ready}`.", "", "This report does not promote an early interval by itself. Identity, instrument, price-action, PIT, source-integrity, test, and CI gates must also pass."])
    write(reports / "research_warmup_coverage.md", "\n".join(warmup_text))
    identity_priority_text = ["# Research identity priority queue", "", "One row is included for every required research security.", "", "| Security | Symbol | Company | First seen | Last seen | Max rank | Liquid dates | Identity quality | ISIN evidence | Name count | Ticker count | Max absent 60d | Recommendation |", "|---|---|---|---|---|---:|---:|---|---|---:|---:|---:|---|"]
    for row in identity_priority_rows:
        sid, symbol, company, first_seen, last_seen, max_rank, liquid_dates, identity_quality, isin_evidence, name_count, symbol_count, max_absent_days, identity_ok = row
        recommendation = "ACCEPT_RESEARCH_IDENTITY" if identity_ok else "REVIEW_REQUIRED"
        identity_priority_text.append(f"| `{sid}` | `{symbol}` | `{company}` | `{first_seen}` | `{last_seen}` | {max_rank} | {liquid_dates} | `{identity_quality}` | `{isin_evidence or ''}` | {name_count} | {symbol_count} | {max_absent_days} | `{recommendation}` |")
    write(reports / "research_identity_priority.md", "\n".join(identity_priority_text))
    pre2013_identity_text = [
        "# Pre-2013 identity priority",
        "",
        "This queue includes only securities that enter `LIQUID_V1` or historical Top-750 before the current 2013 control start.",
        "Low-liquidity unresolved histories outside this scope are not blockers for early-period promotion.",
        "",
        "| Security | Symbol | Company | First research month | Last research month | Candidate ISIN | Identity quality | Best rank | Research months | Episode count | Max absent 60d | Company-name variants | Priority |",
        "|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in pre2013_identity_priority_rows:
        sid, symbol, company, first_month, last_month, candidate_isin, identity_quality, best_rank, months, episode_count, max_absent_days, name_variants, identity_ok = row
        priority_reasons = []
        if not identity_ok:
            priority_reasons.append("IDENTITY_FAILURE")
        if not candidate_isin:
            priority_reasons.append("MISSING_ISIN")
        if episode_count and episode_count > 1:
            priority_reasons.append("MULTI_EPISODE")
        if max_absent_days and max_absent_days > 0:
            priority_reasons.append("SPARSE_OBSERVATIONS")
        priority = "ACCEPT_RESEARCH_IDENTITY" if not priority_reasons else ",".join(priority_reasons)
        pre2013_identity_text.append(f"| `{sid}` | `{symbol}` | `{company}` | {first_month} | {last_month} | `{candidate_isin or ''}` | `{identity_quality}` | {best_rank} | {months} | {episode_count} | {max_absent_days} | {name_variants} | `{priority}` |")
    pre2013_identity_text.extend([
        "",
        "This report is a prioritization queue. Promotion still requires zero required-scope identity failures for the promoted interval.",
    ])
    write(reports / "pre2013_identity_priority.md", "\n".join(pre2013_identity_text))
    episode_audit_text = [
        "# Pre-2013 identity episode audit",
        "",
        "This audit is scoped to securities that enter `LIQUID_V1` or historical Top-750 before the current research control start.",
        "It detects symbol reuse, ISIN reuse, multi-episode rows, source-start left-censoring, and long disappearance/reappearance candidates.",
        "",
        "| Security | Symbol | Company | First seen | Last seen | Episodes | Symbols | ISINs | Name variants | Symbol securities | Symbol ISINs | ISIN securities | ISIN symbols | Max absent official sessions | Flags |",
        "|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in pre2013_episode_audit_rows:
        (
            sid,
            symbol,
            company,
            first_seen,
            last_seen,
            episode_count,
            symbol_count,
            isin_count,
            company_name_count,
            max_symbol_security_count,
            max_symbol_isin_count,
            max_isin_security_count,
            max_isin_symbol_count,
            max_absent_sessions,
            has_left_censored_episode,
        ) = row
        flags = []
        if max_symbol_security_count and max_symbol_security_count > 1:
            flags.append("SYMBOL_REUSE_REVIEW")
        if max_symbol_isin_count and max_symbol_isin_count > 1:
            flags.append("SYMBOL_MULTIPLE_ISIN")
        if max_isin_security_count and max_isin_security_count > 1:
            flags.append("ISIN_MULTIPLE_SECURITIES")
        if max_isin_symbol_count and max_isin_symbol_count > 1:
            flags.append("ISIN_MULTIPLE_SYMBOLS")
        if episode_count and episode_count > 1:
            flags.append("MULTI_EPISODE")
        if company_name_count and company_name_count > 1:
            flags.append("COMPANY_NAME_VARIANTS")
        if max_absent_sessions and max_absent_sessions >= 60:
            flags.append("LONG_GAP_REVIEW")
        if has_left_censored_episode:
            flags.append("LEFT_CENSORED_SOURCE_START")
        if not flags:
            flags.append("NO_EPISODE_RISK_DETECTED")
        episode_audit_text.append(f"| `{sid}` | `{symbol}` | `{company}` | {first_seen} | {last_seen} | {episode_count} | {symbol_count} | {isin_count} | {company_name_count} | {max_symbol_security_count} | {max_symbol_isin_count} | {max_isin_security_count} | {max_isin_symbol_count} | {max_absent_sessions} | `{','.join(flags)}` |")
    episode_audit_text.extend([
        "",
        "`LONG_GAP_REVIEW` uses a 60-official-session diagnostic threshold. It is not an automatic identity split.",
        "Promotion still requires no competing contemporaneous identity or unexplained ticker reuse in the promoted required scope.",
    ])
    write(reports / "pre2013_identity_episode_audit.md", "\n".join(episode_audit_text))
    promotion_text = [
        "# Pre-2013 research identity promotion",
        "",
        f"Scope: `{PRIORITY_SCOPE}`.",
        f"Current control start: `{CURRENT_PROVEN_RESEARCH_START_DATE}`.",
        "",
        "Each row applies the existing research identity gate to required securities from the candidate start through the day before the current control start.",
        "",
        "| Candidate start | First scoped month | Last scoped month | Required securities | RECONSTRUCTED_TRADING_IDENTITY | Other accepted identities | Identity failures | Hard gate |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for row in pre2013_identity_promotion_rows:
        candidate_start, first_month, last_month, required_securities, reconstructed_count, other_accepted_count, failure_count = row
        if not required_securities:
            hard_gate = "NOT_MATERIALIZED"
        elif failure_count == 0:
            hard_gate = "PASS"
        else:
            hard_gate = "FAIL"
        promotion_text.append(f"| {candidate_start} | {first_month or ''} | {last_month or ''} | {required_securities} | {reconstructed_count} | {other_accepted_count} | {failure_count} | `{hard_gate}` |")
    promotion_text.extend([
        "",
        "Hard gate: zero required-scope identity failures for the candidate interval.",
        "`NOT_MATERIALIZED` means the current release does not yet contain monthly candidate snapshots for that interval.",
        "A `PASS` here is necessary but not sufficient; promotion also requires source, warmup, instrument, price-action, PIT invariant, regression, test, and CI gates.",
    ])
    write(reports / "pre2013_research_identity_promotion.md", "\n".join(promotion_text))
    adjustment_quality_text = [
        "# Pre-2013 adjusted-return quality",
        "",
        "This report evaluates material price-action and adjusted-return risks for candidate starts before the current research control start.",
        f"Primary signal series: `{RECOMMENDED_SIGNAL_PRICE_SERIES}`.",
        f"Maximum configured lookback window: `{max(FEATURE_READINESS_WINDOWS.values())}` official sessions.",
        "",
        "## Candidate material price-action gate",
        "",
        "| Candidate start | Material events in candidate or lookback scope | Missing factors | Non-PASS boundaries | Left-censored boundaries | Non-PASS without observed crossing | Contaminating signal-window non-PASS | Gate |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    adjustment_rows_by_candidate = {str(row[0]): row for row in pre2013_adjustment_candidate_rows}
    for candidate_start in CANDIDATE_RESEARCH_START_DATES:
        row = adjustment_rows_by_candidate.get(candidate_start)
        if row is None:
            material_events = missing_factors = non_pass_boundaries = left_censored_boundaries = possible_signal_boundaries = no_crossing_boundaries = contaminating_boundaries = 0
        else:
            _candidate, material_events, missing_factors, non_pass_boundaries, left_censored_boundaries, possible_signal_boundaries, no_crossing_boundaries, contaminating_boundaries = row
        if missing_factors:
            gate = "FAIL_MISSING_FACTORS"
        elif contaminating_boundaries:
            gate = "REVIEW_REQUIRED"
        else:
            gate = "PASS"
        adjustment_quality_text.append(f"| {candidate_start} | {material_events} | {missing_factors} | {non_pass_boundaries} | {left_censored_boundaries} | {no_crossing_boundaries} | {contaminating_boundaries} | `{gate}` |")
    adjustment_quality_text.extend([
        "",
        "## Adjusted one-session return outliers",
        "",
        "Outliers are prioritized only for pre-2013 required-scope securities. They are not automatically removed.",
        "",
        "| Security | Symbol | Company | Date | Adjusted return | Classification |",
        "|---|---|---|---|---:|---|",
    ])
    for sid, symbol, company, date, adjusted_return, classification in pre2013_adjusted_outlier_rows:
        adjustment_quality_text.append(f"| `{sid}` | `{symbol}` | `{company}` | {date} | {adjusted_return:.6f} | `{classification}` |")
    adjustment_quality_text.extend([
        "",
        "`CORPORATE_ACTION_ADJACENT` means the outlier is near an official split, reverse split, or bonus date and needs boundary interpretation, not deletion.",
        "This report does not use dividends as a hard gate. Price-return adjusted close remains the promoted signal series.",
    ])
    write(reports / "pre2013_adjusted_return_quality.md", "\n".join(adjustment_quality_text))
    instrument_text = [
        "# Pre-2013 instrument classification audit",
        "",
        "This audit is scoped to securities that enter `LIQUID_V1` or historical Top-750 before the current research control start.",
        "The ordinary-equity gate fails closed for known non-common-equity instruments and ambiguous required-scope classifications.",
        "",
        "## Candidate instrument gate",
        "",
        "| Candidate start | Required securities | Non-ordinary securities | Ambiguous quality | Known product symbols | Product-like false-positive review | Gate |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    instrument_rows_by_candidate = {str(row[0]): row for row in pre2013_instrument_candidate_rows}
    for candidate_start in CANDIDATE_RESEARCH_START_DATES:
        row = instrument_rows_by_candidate.get(candidate_start)
        if row is None:
            required_securities = non_ordinary = ambiguous_quality = known_product_symbols = product_like_ordinary_review = 0
        else:
            _candidate, required_securities, non_ordinary, ambiguous_quality, known_product_symbols, product_like_ordinary_review = row
        if non_ordinary or known_product_symbols:
            gate = "FAIL_NON_ORDINARY"
        elif ambiguous_quality:
            gate = "FAIL_AMBIGUOUS"
        elif not required_securities:
            gate = "NOT_MATERIALIZED"
        else:
            gate = "PASS"
        instrument_text.append(f"| {candidate_start} | {required_securities} | {non_ordinary} | {ambiguous_quality} | {known_product_symbols} | {product_like_ordinary_review} | `{gate}` |")
    instrument_text.extend([
        "",
        "## Review queue",
        "",
        "| Security | Symbol | Company | First month | Last month | Instrument type | Instrument quality | Best rank | Research months | Product-like marker | Known product symbol | Review flag |",
        "|---|---|---|---|---|---|---|---:|---:|---|---|---|",
    ])
    for row in pre2013_instrument_review_rows:
        sid, symbol, company, first_month, last_month, instrument_type_value, instrument_quality, best_rank, research_months, product_like_marker, known_product_symbol = row
        flags = []
        if instrument_type_value != "ORDINARY_EQUITY":
            flags.append("NON_ORDINARY_IN_REQUIRED_SCOPE")
        if instrument_quality is None or instrument_quality == "UNRESOLVED":
            flags.append("AMBIGUOUS_INSTRUMENT_QUALITY")
        if known_product_symbol:
            flags.append("KNOWN_PRODUCT_SYMBOL_REBUILD_REQUIRED")
        if product_like_marker:
            flags.append("PRODUCT_LIKE_NAME_REVIEW")
        instrument_text.append(f"| `{sid}` | `{symbol}` | `{company}` | {first_month} | {last_month} | `{instrument_type_value}` | `{instrument_quality}` | {best_rank} | {research_months} | `{product_like_marker}` | `{known_product_symbol}` | `{','.join(flags)}` |")
    instrument_text.extend([
        "",
        "Product-like markers are a review signal only. They do not override source-backed instrument classification by themselves.",
        "Known product symbols are exact-symbol ETF/product blockers and require a source rebuild so they leave the ordinary-equity release artifacts.",
        "Promotion requires zero known non-ordinary and zero ambiguous classifications inside the promoted required scope.",
    ])
    write(reports / "pre2013_instrument_classification_audit.md", "\n".join(instrument_text))
    terminal_priority_text = [
        "# Pre-2013 terminal event priority",
        "",
        "This queue is scoped to pre-2013 `LIQUID_V1` or historical Top-750 securities that later disappear from official observations.",
        "Terminal uncertainty does not remove a security from historical price-return research. It creates explicit downstream recovery-sensitivity work for portfolio research.",
        "",
        "| Security | Symbol | Company | First required month | Last required month | Best rank | Research months | LIQUID_V1 | Top-750 | Last observed | Terminal reference date | Terminal evidence | Terminal value quality | Priority |",
        "|---|---|---|---|---|---:|---:|---|---|---|---|---|---|---|",
    ]
    for row in pre2013_terminal_priority_rows:
        (
            sid,
            symbol,
            company,
            first_month,
            last_month,
            best_rank,
            research_months,
            enters_liquid_v1,
            enters_top750,
            last_observed,
            terminal_reference_date,
            terminal_types,
            terminal_value_quality,
        ) = row
        if terminal_value_quality in {"UNKNOWN", "UNRESOLVED"} or "UNKNOWN_TERMINAL_EVENT" in str(terminal_types):
            priority = "RECOVERY_SENSITIVITY_REQUIRED"
        else:
            priority = "DOCUMENTED_TERMINAL_EVIDENCE"
        terminal_priority_text.append(f"| `{sid}` | `{symbol}` | `{company}` | {first_month} | {last_month} | {best_rank} | {research_months} | `{enters_liquid_v1}` | `{enters_top750}` | {last_observed} | {terminal_reference_date} | `{terminal_types}` | `{terminal_value_quality}` | `{priority}` |")
    terminal_priority_text.extend([
        "",
        "Allowed downstream recovery scenarios remain `ZERO_RECOVERY`, `LAST_OBSERVED_PRICE`, and `DOCUMENTED_VALUE`.",
        "This report prioritizes high-liquidity historical disappearances; it does not require resolving all low-liquidity terminal events before promotion.",
    ])
    write(reports / "pre2013_terminal_event_priority.md", "\n".join(terminal_priority_text))
    survivorship_text = [
        "# Pre-2013 survivorship evidence",
        "",
        "This report demonstrates that early historical universes are not built from current survivors.",
        "",
        "## Current-survivor comparison by early year",
        "",
        "| Year | Required securities | Current survivors | Non-survivors | LIQUID_V1 securities | Top-750 securities |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for year, required_securities, current_survivors, non_survivors, liquid_count, top750_count in pre2013_survivorship_year_rows:
        survivorship_text.append(f"| {year} | {required_securities} | {current_survivors} | {non_survivors} | {liquid_count} | {top750_count} |")
    survivorship_text.extend([
        "",
        "## Example historical non-survivors retained in early snapshots",
        "",
        "| Security | Symbol | Company | First required month | Last required month | Best rank | LIQUID_V1 | Top-750 | Last observed | Terminal evidence |",
        "|---|---|---|---|---|---:|---|---|---|---|",
    ])
    for row in pre2013_survivorship_example_rows:
        sid, symbol, company, first_month, last_month, best_rank, enters_liquid_v1, enters_top750, last_observed, terminal_types = row
        survivorship_text.append(f"| `{sid}` | `{symbol}` | `{company}` | {first_month} | {last_month} | {best_rank} | `{enters_liquid_v1}` | `{enters_top750}` | {last_observed} | `{terminal_types}` |")
    survivorship_text.extend([
        "",
        "Current survival is used only as a QA comparison. It never constructs historical membership.",
    ])
    write(reports / "pre2013_survivorship_evidence.md", "\n".join(survivorship_text))
    dates = sorted({row[0] for row in monthly_detail_rows})
    by_date = {point: {row[1] for row in monthly_detail_rows if row[0] == point and row[2]} for point in dates}
    top750_by_date = {point: {row[1] for row in monthly_detail_rows if row[0] == point and row[3]} for point in dates}
    pre2013_dates = [point for point in dates if str(point) < CURRENT_PROVEN_RESEARCH_START_DATE]
    pre2013_by_date = {point: by_date[point] for point in pre2013_dates}
    pre2013_top750_by_date = {point: top750_by_date[point] for point in pre2013_dates}
    pre2013_stability_text = [
        "# Pre-2013 research universe stability",
        "",
        "Monthly entry, exit, and turnover counts use the PIT `LIQUID_V1` membership before the current research control start.",
        "Top-750 overlap is the Jaccard overlap of consecutive monthly PIT Top-750 sets.",
        "",
        "| Date | LIQUID_V1 size | Entries | Exits | Turnover | Top-750 size | Top-750 Jaccard overlap | Large-discontinuity flag |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    previous_liquid: set[str] = set()
    previous_top750: set[str] = set()
    for point in pre2013_dates:
        current_liquid = pre2013_by_date[point]
        current_top750 = pre2013_top750_by_date[point]
        entries = len(current_liquid - previous_liquid)
        exits = len(previous_liquid - current_liquid)
        denominator = max(1, (len(current_liquid) + len(previous_liquid)) / 2)
        turnover = (entries + exits) / denominator
        top750_union = len(current_top750 | previous_top750)
        top750_overlap = len(current_top750 & previous_top750) / max(1, top750_union)
        flags = []
        if turnover > 0.25 and previous_liquid:
            flags.append("LARGE_LIQUID_V1_TURNOVER")
        if top750_overlap < 0.70 and previous_top750:
            flags.append("LOW_TOP750_OVERLAP")
        if not flags:
            flags.append("OK")
        pre2013_stability_text.append(f"| {point} | {len(current_liquid)} | {entries} | {exits} | {turnover:.4f} | {len(current_top750)} | {top750_overlap:.4f} | `{','.join(flags)}` |")
        previous_liquid = current_liquid
        previous_top750 = current_top750
    pre2013_stability_text.extend([
        "",
        "Large discontinuity flags are diagnostic. They trigger investigation but do not automatically prove a PIT violation.",
        "`NOT_MATERIALIZED` early candidate periods will appear as missing months rather than synthetic zero-size universes.",
    ])
    write(reports / "pre2013_research_universe_stability.md", "\n".join(pre2013_stability_text))
    count_text = [
        "# Pre-2013 historical universe counts",
        "",
        "Counts are derived from historical monthly PIT snapshots before the current research control start.",
        "They are not index membership and are not forced to 500 securities.",
        "",
        "| Year | Active ordinary | Fully seasoned observed history | 300-session ready | LIQUID_V1 | Top-500 | Top-750 | Top-1000 | Required scope | 252-signal ready | 273-signal ready |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in pre2013_historical_count_rows:
        (
            year,
            active_ordinary,
            fully_seasoned,
            model_handoff_ready,
            liquid_v1,
            top500,
            top750,
            top1000,
            required_scope_count,
            signal_ready_252,
            signal_ready_273,
        ) = row
        count_text.append(f"| {year} | {active_ordinary} | {fully_seasoned} | {model_handoff_ready} | {liquid_v1} | {top500} | {top750} | {top1000} | {required_scope_count} | {signal_ready_252} | {signal_ready_273} |")
    count_text.extend([
        "",
        "`Fully seasoned observed history` uses observed sessions only. Left-censored securities can have older true listing age but still lack pre-source price history.",
        "`Required scope` is `LIQUID_V1_OR_HISTORICAL_TOP750`; low-liquidity names outside that scope do not block early promotion.",
    ])
    write(reports / "pre2013_historical_universe_counts.md", "\n".join(count_text))
    overlap_values = []
    for previous, current in zip(dates, dates[1:]):
        overlap_values.append(len(top750_by_date[previous] & top750_by_date[current]) / max(1, len(top750_by_date[previous] | top750_by_date[current])))
    stability_text = ["# Research universe stability", "", "Monthly entry, exit, and turnover counts use the PIT `LIQUID_V1` membership.", "", "| Date | Size | Entries | Exits | Turnover |", "|---|---:|---:|---:|---:|"]
    previous = set()
    for point in dates:
        current = by_date[point]
        entries, exits = len(current - previous), len(previous - current)
        denominator = max(1, (len(current) + len(previous)) / 2)
        stability_text.append(f"| {point} | {len(current)} | {entries} | {exits} | {(entries + exits) / denominator:.4f} |")
        previous = current
    write(reports / "research_universe_stability.md", "\n".join(stability_text))
    survivor_text = ["# Survivorship audit", "", f"Historically observed security IDs that do not have an observation on the latest source date: `{disappeared_count}`.", "", "| Security | Symbol | Last liquid date | Last observed date | Terminal evidence |", "|---|---|---|---|---|"]
    survivor_text.extend(f"| `{sid}` | `{symbol}` | {eligible_date} | {observed_date} | `{terminal_types}` |" for sid, symbol, eligible_date, observed_date, terminal_types in disappeared_rows)
    write(reports / "survivorship_audit.md", "\n".join(survivor_text))
    write(reports / "current_survivor_comparison.md", f"""# Current-survivor comparison

- Unique securities entering `LIQUID_V1`: `{historical_eligible}`.
- Securities still observed on the latest source date: `{current_survivor_eligible}`.
- Historical eligible securities not observed on the latest source date: `{historical_eligible - current_survivor_eligible}`.

This is a QA comparison only. The current survivor set does not construct historical membership.
""")
    average_size = sum(len(values) for values in by_date.values()) / max(1, len(by_date))
    sizes = [len(values) for values in by_date.values()]
    write(reports / "research_scale.md", f"""# Research universe scale

- Monthly snapshots: `{len(by_date)}`.
- Average `LIQUID_V1` size: `{average_size:.1f}`.
- Minimum size: `{min(sizes) if sizes else 0}`.
- Maximum size: `{max(sizes) if sizes else 0}`.
- Unique `LIQUID_V1` securities: `{historical_eligible}`.
- Later-disappeared observed securities: `{disappeared_count}`.
- Current-date survivors among historical eligible securities: `{current_survivor_eligible}`.
- Average month-to-month Top-750 Jaccard overlap: `{sum(overlap_values) / max(1, len(overlap_values)):.4f}`.
- Top-750 overlap observations: `{len(overlap_values)}`.
- Required securities needing terminal-event sensitivity: `{terminal_sensitivity_count}`.

Top-750 overlap is the intersection divided by the union of consecutive monthly PIT Top-750 sets. Terminal-event sensitivity includes required securities with an unknown or unresolved terminal value.
""")
    baseline_required = [
        baseline_release / RESEARCH_UNIVERSE_MONTHLY_ARTIFACT,
        baseline_release / ADJUSTED_PRICE_ARTIFACT,
        baseline_release / CORPORATE_ACTIONS_ARTIFACT,
    ]
    regression_text = [
        "# v2.0.1 regression comparison",
        "",
        f"Baseline release: `{baseline_release}`.",
        f"Candidate release: `{release}`.",
        f"Comparison interval: `{CURRENT_PROVEN_RESEARCH_START_DATE}` through `{CURRENT_PROVEN_RESEARCH_END_DATE}`.",
        "",
    ]
    if all(path.exists() for path in baseline_required):
        regression_connection = duckdb.connect()
        try:
            universe_count_diffs = scalar(regression_connection, f"""
              WITH baseline AS (
                SELECT CAST(date AS DATE) AS date,
                  COUNT(DISTINCT security_id) AS monthly_rows,
                  COUNT(DISTINCT security_id) FILTER (WHERE NSE_BROAD_LIQUID_PIT_V1_eligible) AS liquid_count,
                  COUNT(DISTINCT security_id) FILTER (WHERE top750_liquidity) AS top750_count
                FROM read_parquet('{baseline_r}/research_universe_monthly.parquet')
                WHERE CAST(date AS DATE) BETWEEN DATE '{CURRENT_PROVEN_RESEARCH_START_DATE}' AND DATE '{CURRENT_PROVEN_RESEARCH_END_DATE}'
                GROUP BY 1
              ), candidate AS (
                SELECT CAST(date AS DATE) AS date,
                  COUNT(DISTINCT security_id) AS monthly_rows,
                  COUNT(DISTINCT security_id) FILTER (WHERE NSE_BROAD_LIQUID_PIT_V1_eligible) AS liquid_count,
                  COUNT(DISTINCT security_id) FILTER (WHERE top750_liquidity) AS top750_count
                FROM read_parquet('{r}/research_universe_monthly.parquet')
                WHERE CAST(date AS DATE) BETWEEN DATE '{CURRENT_PROVEN_RESEARCH_START_DATE}' AND DATE '{CURRENT_PROVEN_RESEARCH_END_DATE}'
                GROUP BY 1
              )
              SELECT COUNT(*)
              FROM baseline b
              FULL OUTER JOIN candidate c USING (date)
              WHERE COALESCE(b.monthly_rows, -1) <> COALESCE(c.monthly_rows, -1)
                 OR COALESCE(b.liquid_count, -1) <> COALESCE(c.liquid_count, -1)
                 OR COALESCE(b.top750_count, -1) <> COALESCE(c.top750_count, -1)
            """)
            liquid_membership_diffs = scalar(regression_connection, f"""
              WITH baseline AS (
                SELECT CAST(date AS DATE) AS date, security_id
                FROM read_parquet('{baseline_r}/research_universe_monthly.parquet')
                WHERE CAST(date AS DATE) BETWEEN DATE '{CURRENT_PROVEN_RESEARCH_START_DATE}' AND DATE '{CURRENT_PROVEN_RESEARCH_END_DATE}'
                  AND NSE_BROAD_LIQUID_PIT_V1_eligible
              ), candidate AS (
                SELECT CAST(date AS DATE) AS date, security_id
                FROM read_parquet('{r}/research_universe_monthly.parquet')
                WHERE CAST(date AS DATE) BETWEEN DATE '{CURRENT_PROVEN_RESEARCH_START_DATE}' AND DATE '{CURRENT_PROVEN_RESEARCH_END_DATE}'
                  AND NSE_BROAD_LIQUID_PIT_V1_eligible
              )
              SELECT COUNT(*)
              FROM baseline b
              FULL OUTER JOIN candidate c USING (date, security_id)
              WHERE b.security_id IS NULL OR c.security_id IS NULL
            """)
            top750_membership_diffs = scalar(regression_connection, f"""
              WITH baseline AS (
                SELECT CAST(date AS DATE) AS date, security_id
                FROM read_parquet('{baseline_r}/research_universe_monthly.parquet')
                WHERE CAST(date AS DATE) BETWEEN DATE '{CURRENT_PROVEN_RESEARCH_START_DATE}' AND DATE '{CURRENT_PROVEN_RESEARCH_END_DATE}'
                  AND top750_liquidity
              ), candidate AS (
                SELECT CAST(date AS DATE) AS date, security_id
                FROM read_parquet('{r}/research_universe_monthly.parquet')
                WHERE CAST(date AS DATE) BETWEEN DATE '{CURRENT_PROVEN_RESEARCH_START_DATE}' AND DATE '{CURRENT_PROVEN_RESEARCH_END_DATE}'
                  AND top750_liquidity
              )
              SELECT COUNT(*)
              FROM baseline b
              FULL OUTER JOIN candidate c USING (date, security_id)
              WHERE b.security_id IS NULL OR c.security_id IS NULL
            """)
            signal_price_diffs = scalar(regression_connection, f"""
              WITH baseline AS (
                SELECT CAST(date AS DATE) AS date, security_id, research_adjusted_close AS price_return_adjusted_close
                FROM read_parquet('{baseline_r}/daily_prices_adjusted.parquet')
                WHERE CAST(date AS DATE) BETWEEN DATE '{CURRENT_PROVEN_RESEARCH_START_DATE}' AND DATE '{CURRENT_PROVEN_RESEARCH_END_DATE}'
              ), candidate AS (
                SELECT CAST(date AS DATE) AS date, security_id, research_adjusted_close AS price_return_adjusted_close
                FROM read_parquet('{r}/daily_prices_adjusted.parquet')
                WHERE CAST(date AS DATE) BETWEEN DATE '{CURRENT_PROVEN_RESEARCH_START_DATE}' AND DATE '{CURRENT_PROVEN_RESEARCH_END_DATE}'
              )
              SELECT COUNT(*)
              FROM baseline b
              FULL OUTER JOIN candidate c USING (date, security_id)
              WHERE b.security_id IS NULL OR c.security_id IS NULL
                 OR ABS(COALESCE(b.price_return_adjusted_close, -1) - COALESCE(c.price_return_adjusted_close, -1)) > 0.000001
            """)
            corporate_factor_diffs = scalar(regression_connection, f"""
              WITH baseline AS (
                SELECT security_id, CAST(event_date AS DATE) AS event_date, event_type, price_factor, share_factor
                FROM read_parquet('{baseline_r}/corporate_actions.parquet')
                WHERE CAST(event_date AS DATE) BETWEEN DATE '{CURRENT_PROVEN_RESEARCH_START_DATE}' AND DATE '{CURRENT_PROVEN_RESEARCH_END_DATE}'
                  AND event_type IN {MATERIAL_ACTIONS}
              ), candidate AS (
                SELECT security_id, CAST(event_date AS DATE) AS event_date, event_type, price_factor, share_factor
                FROM read_parquet('{r}/corporate_actions.parquet')
                WHERE CAST(event_date AS DATE) BETWEEN DATE '{CURRENT_PROVEN_RESEARCH_START_DATE}' AND DATE '{CURRENT_PROVEN_RESEARCH_END_DATE}'
                  AND event_type IN {MATERIAL_ACTIONS}
              )
              SELECT COUNT(*)
              FROM baseline b
              FULL OUTER JOIN candidate c USING (security_id, event_date, event_type)
              WHERE b.security_id IS NULL OR c.security_id IS NULL
                 OR ABS(COALESCE(b.price_factor, -1) - COALESCE(c.price_factor, -1)) > 0.000001
                 OR ABS(COALESCE(b.share_factor, -1) - COALESCE(c.share_factor, -1)) > 0.000001
            """)
        finally:
            regression_connection.close()
        regression_status = "PASS" if (
            int(universe_count_diffs) == 0
            and int(liquid_membership_diffs) == 0
            and int(top750_membership_diffs) == 0
            and int(signal_price_diffs) == 0
            and int(corporate_factor_diffs) == 0
        ) else "REVIEW_REQUIRED"
        regression_text.extend([
            "| Check | Difference rows |",
            "|---|---:|",
            f"| Monthly universe counts | {universe_count_diffs} |",
            f"| LIQUID_V1 membership | {liquid_membership_diffs} |",
            f"| Top-750 membership | {top750_membership_diffs} |",
            f"| Signal price series | {signal_price_diffs} |",
            f"| Material corporate-action factors | {corporate_factor_diffs} |",
            "",
            f"Regression status: `{regression_status}`.",
        ])
    else:
        regression_status = "BASELINE_NOT_AVAILABLE"
        missing_baseline = [str(path) for path in baseline_required if not path.exists()]
        regression_text.extend([
            "Regression status: `BASELINE_NOT_AVAILABLE`.",
            "",
            "Missing baseline artifacts:",
            "",
        ])
        regression_text.extend(f"- `{path}`" for path in missing_baseline)
        regression_text.extend([
            "",
            "This is an explicit non-pass state. A promoted release must compare against v2.0.1 before changing the proven 2013+ scope.",
        ])
    write(reports / "v2_0_1_regression_comparison.md", "\n".join(regression_text))
    identity_gate_by_candidate = {}
    for row in pre2013_identity_promotion_rows:
        candidate_start, _first_month, _last_month, required_securities, _reconstructed_count, _other_accepted_count, failure_count = row
        if not required_securities:
            identity_gate_by_candidate[str(candidate_start)] = "NOT_MATERIALIZED"
        elif failure_count == 0:
            identity_gate_by_candidate[str(candidate_start)] = "PASS"
        else:
            identity_gate_by_candidate[str(candidate_start)] = "FAIL"
    adjustment_gate_by_candidate = {}
    adjustment_rows_by_candidate = {str(row[0]): row for row in pre2013_adjustment_candidate_rows}
    for candidate_start in CANDIDATE_RESEARCH_START_DATES:
        row = adjustment_rows_by_candidate.get(candidate_start)
        if row is None:
            adjustment_gate_by_candidate[candidate_start] = "PASS"
            continue
        _candidate, _material_events, missing_factors, _non_pass_boundaries, _left_censored_boundaries, _possible_signal_boundaries, _no_crossing_boundaries, contaminating_boundaries = row
        if missing_factors:
            adjustment_gate_by_candidate[candidate_start] = "FAIL_MISSING_FACTORS"
        elif contaminating_boundaries:
            adjustment_gate_by_candidate[candidate_start] = "REVIEW_REQUIRED"
        else:
            adjustment_gate_by_candidate[candidate_start] = "PASS"
    instrument_gate_by_candidate = {}
    instrument_rows_by_candidate = {str(row[0]): row for row in pre2013_instrument_candidate_rows}
    for candidate_start in CANDIDATE_RESEARCH_START_DATES:
        row = instrument_rows_by_candidate.get(candidate_start)
        if row is None:
            instrument_gate_by_candidate[candidate_start] = "NOT_MATERIALIZED"
            continue
        _candidate, required_securities, non_ordinary, ambiguous_quality, known_product_symbols, _product_like_ordinary_review = row
        if non_ordinary or known_product_symbols:
            instrument_gate_by_candidate[candidate_start] = "FAIL_NON_ORDINARY"
        elif ambiguous_quality:
            instrument_gate_by_candidate[candidate_start] = "FAIL_AMBIGUOUS"
        elif not required_securities:
            instrument_gate_by_candidate[candidate_start] = "NOT_MATERIALIZED"
        else:
            instrument_gate_by_candidate[candidate_start] = "PASS"
    feature_ready_dates = warmup_coverage.get("feature_ready_dates", {})
    earliest_fully_warmed = warmup_coverage.get("earliest_fully_warmed_date")
    pre2006_available_text = "YES" if pre2006_valid else "NO"
    candidate_audit_by_start = {}
    if candidate_promotion_audit_path.exists():
        candidate_audit_report = json.loads(candidate_promotion_audit_path.read_text(encoding="utf-8"))
        candidate_audit_by_start = {
            str(item.get("candidate_start")): item
            for item in candidate_audit_report.get("candidate_audits", [])
            if isinstance(item, dict)
        }
    research_interval_text = []
    if research_quality_intervals:
        for interval in research_quality_intervals:
            research_interval_text.append(
                f"- `{interval.get('start')}` through `{interval.get('end')}`: `{interval.get('status')}` "
                f"for `{interval.get('profile')}` / `{interval.get('profile_version')}`"
            )
    else:
        research_interval_text.append("- No explicit research-quality intervals are present in the current manifest.")
    candidate_decision_text = [
        "| Candidate start | Candidate audit | Decision-window gate | Warmup gate | Session-liquidity gate | Identity gate | Price-action gate | Instrument gate | Status gate | Hard failures | Promotion interpretation |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    candidate_promotion_decisions = []
    for candidate_start in CANDIDATE_RESEARCH_START_DATES:
        identity_gate = identity_gate_by_candidate.get(candidate_start, CANDIDATE_NOT_MATERIALIZED_INTERPRETATION)
        adjustment_gate = adjustment_gate_by_candidate.get(candidate_start, CANDIDATE_NOT_MATERIALIZED_INTERPRETATION)
        instrument_gate = instrument_gate_by_candidate.get(candidate_start, CANDIDATE_NOT_MATERIALIZED_INTERPRETATION)
        candidate_audit = candidate_audit_by_start.get(candidate_start)
        hard_failures = candidate_audit.get("hard_failures", {}) if candidate_audit else {
            **{key: True for key in CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS},
            **{key: 0 for key in CANDIDATE_NUMERIC_HARD_FAILURE_KEYS},
        }
        price_action_evidence = candidate_audit.get("price_action_evidence", {}) if candidate_audit else {
            "price_adjustment_failures": 0,
            "material_missing_factors": 0,
            "material_events": 0,
            "signal_window_non_pass_boundaries": 0,
            "price_action_gate_pass": False,
            "boundary_validation_review_required": True,
        }
        feature_readiness = candidate_audit.get("feature_readiness", {}) if candidate_audit else {
            "feature_warmup_not_ready": True,
            "required_prior_sessions_for_full_readiness": max(FEATURE_READINESS_WINDOWS.values()),
            "first_decision_session_index": None,
            "fully_warmed_required_rows": 0,
            "required_rows": 0,
            "row_level_not_fully_warmed_required_rows": 0,
            "signal_ready_252_rows": 0,
            "signal_ready_273_rows": 0,
            "model_handoff_history_ready_300_rows": 0,
        }
        refined_boundary = candidate_audit.get("refined_earliest_passing_snapshot") if candidate_audit else None
        candidate_audit_status = candidate_audit.get("status", CANDIDATE_NOT_RECORDED_VALUE) if candidate_audit else CANDIDATE_NOT_RECORDED_VALUE
        if not candidate_audit:
            decision_window_gate = CANDIDATE_NOT_RECORDED_VALUE
            warmup_gate = CANDIDATE_NOT_RECORDED_VALUE
            session_gate = CANDIDATE_NOT_RECORDED_VALUE
            status_gate = CANDIDATE_NOT_RECORDED_VALUE
            pit_universe_gate_pass = False
            research_candidate_gate_pass = False
            feature_model_readiness_complete = False
            hard_failure_summary = "NO_CANDIDATE_AUDIT_ROW"
        else:
            decision_window_gate = CANDIDATE_PASS_VALUE if hard_failures.get("decision_window_snapshots_missing") is False else CANDIDATE_FAIL_VALUE
            warmup_gate = CANDIDATE_PASS_VALUE if (
                feature_readiness.get("feature_warmup_not_ready") is False
                and hard_failures.get("decision_window_snapshots_missing") is False
            ) else CANDIDATE_FAIL_VALUE
            session_failure_count = int(hard_failures.get("session_liquidity_window_failures") or 0)
            session_gate = CANDIDATE_PASS_VALUE if session_failure_count == 0 else CANDIDATE_FAIL_VALUE
            status_failure_count = int(hard_failures.get("status_failures") or 0)
            status_gate = CANDIDATE_PASS_VALUE if status_failure_count == 0 else CANDIDATE_FAIL_VALUE
            active_hard_failures = [
                f"{key}={value}" for key, value in sorted(hard_failures.items())
                if value is True or (isinstance(value, int) and value != 0)
            ]
            active_price_action_review = [
                f"price_action.{key}={value}" for key, value in sorted(price_action_evidence.items())
                if key in {"price_adjustment_failures", "material_missing_factors", "contaminating_signal_window_non_pass_boundaries"}
                and isinstance(value, int)
                and value != 0
            ]
            pit_universe_gate_pass = candidate_audit.get("pit_universe_gate_pass") is True
            research_candidate_gate_pass = candidate_audit.get("research_candidate_gate_pass") is True
            feature_model_readiness_complete = candidate_audit.get("feature_model_readiness_complete") is True
            hard_failure_summary = ", ".join(active_hard_failures + active_price_action_review) if active_hard_failures or active_price_action_review else "none"
        first_class_gate_values = {
            "decision_window_gate": decision_window_gate,
            "warmup_gate": warmup_gate,
            "session_liquidity_gate": session_gate,
            "identity_gate": identity_gate,
            "price_action_gate": adjustment_gate,
            "instrument_gate": instrument_gate,
            "status_gate": status_gate,
        }
        if candidate_audit and candidate_audit.get("research_candidate_gate_pass") is True and all(first_class_gate_values[gate] == CANDIDATE_PASS_VALUE for gate in CANDIDATE_DECISION_GATE_KEYS):
            interpretation = CANDIDATE_GATE_PASS_INTERPRETATION
        elif candidate_audit_status == CANDIDATE_NOT_RECORDED_VALUE:
            interpretation = CANDIDATE_AUDIT_NOT_RECORDED_INTERPRETATION
        elif CANDIDATE_NOT_MATERIALIZED_INTERPRETATION in {identity_gate, adjustment_gate, instrument_gate}:
            interpretation = CANDIDATE_NOT_MATERIALIZED_INTERPRETATION
        else:
            interpretation = CANDIDATE_NOT_READY_INTERPRETATION
        candidate_promotion_decisions.append({
            "candidate_start": candidate_start,
            "candidate_audit_status": candidate_audit_status,
            "decision_window_gate": decision_window_gate,
            "warmup_gate": warmup_gate,
            "session_liquidity_gate": session_gate,
            "identity_gate": identity_gate,
            "price_action_gate": adjustment_gate,
            "instrument_gate": instrument_gate,
            "status_gate": status_gate,
            "feature_readiness": feature_readiness,
            "feature_model_readiness_complete": feature_model_readiness_complete,
            "refined_earliest_passing_snapshot": refined_boundary,
            "hard_failures": hard_failures,
            "price_action_evidence": price_action_evidence,
            "pit_universe_gate_pass": pit_universe_gate_pass,
            "research_candidate_gate_pass": research_candidate_gate_pass,
            "promotion_interpretation": interpretation,
        })
        candidate_decision_text.append(f"| {candidate_start} | `{candidate_audit_status}` | `{decision_window_gate}` | `{warmup_gate}` | `{session_gate}` | `{identity_gate}` | `{adjustment_gate}` | `{instrument_gate}` | `{status_gate}` | `{hard_failure_summary}` | `{interpretation}` |")
    pass_candidate_starts = sorted(
        item["candidate_start"] for item in candidate_promotion_decisions
        if item.get("candidate_audit_status") == CANDIDATE_PASS_VALUE
        and item.get("research_candidate_gate_pass") is True
    )
    earliest_candidate_gate_pass_start = pass_candidate_starts[0] if pass_candidate_starts else None
    pit_candidate_starts = sorted(
        item["candidate_start"] for item in candidate_promotion_decisions
        if item.get("pit_universe_gate_pass") is True
    )
    earliest_pit_universe_gate_pass_start = pit_candidate_starts[0] if pit_candidate_starts else None
    refined_candidate_boundaries = sorted(
        str(item["refined_earliest_passing_snapshot"])
        for item in candidate_promotion_decisions
        if item.get("refined_earliest_passing_snapshot")
    )
    refined_earliest_candidate_gate_pass_boundary = refined_candidate_boundaries[0] if refined_candidate_boundaries else None
    promotion_requested = bool(args.promote_research_start)
    promotion_start_is_gate_pass = (
        any(candidate_start <= args.promote_research_start for candidate_start in pass_candidate_starts)
        and (
            not refined_earliest_candidate_gate_pass_boundary
            or args.promote_research_start >= refined_earliest_candidate_gate_pass_boundary
        )
        if args.promote_research_start
        else False
    )
    promotion_gate_pass = (
        promotion_requested
        and promotion_start_is_gate_pass
        and hard_evidence_gate_pass
        and validation_ok
        and test_ok
        and ci_ok
    )
    if promotion_requested and not promotion_gate_pass:
        blockers = []
        if not promotion_start_is_gate_pass:
            blockers.append("promote_research_start_not_in_gate_pass_candidates")
        if not hard_evidence_gate_pass:
            blockers.append("hard_evidence_gate_failed")
        if not validation_ok:
            blockers.append("research_invariant_validation_not_pass")
        if not test_ok:
            blockers.append("junit_tests_not_pass")
        if not ci_ok:
            blockers.append("ci_status_not_pass_for_current_git_sha")
        raise SystemExit(f"Cannot promote {args.promote_research_start}: {', '.join(blockers)}")
    quality = RESEARCH_HIGH_CONFIDENCE_STATUS if promotion_gate_pass else RESEARCH_EXPLORATORY_STATUS
    candidate_recommended_research_interval = {
        "status": "CANDIDATE_RESEARCH_GATE_PASS_AVAILABLE" if earliest_candidate_gate_pass_start else "NO_RESEARCH_GATE_PASS",
        "start": earliest_candidate_gate_pass_start,
        "end": str(coverage[1]),
        "profile": PROFILE_ID,
        "profile_version": PROFILE_VERSION,
        "boundary_scan_method": CANDIDATE_REFINED_BOUNDARY_SCAN_METHOD,
        "promotion_status": "NOT_PROMOTED_UNLESS_PRESENT_IN_RESEARCH_QUALITY_INTERVALS",
    }
    candidate_recommended_pit_universe_interval = {
        "status": "CANDIDATE_REFINED_BOUNDARY_AVAILABLE" if refined_earliest_candidate_gate_pass_boundary else "NO_REFINED_BOUNDARY",
        "start": refined_earliest_candidate_gate_pass_boundary,
        "end": str(coverage[1]),
        "profile": PROFILE_ID,
        "profile_version": PROFILE_VERSION,
        "boundary_scan_method": CANDIDATE_REFINED_BOUNDARY_SCAN_METHOD,
        "promotion_status": "NOT_PROMOTED_UNLESS_PRESENT_IN_RESEARCH_QUALITY_INTERVALS",
        "interval_type": CANDIDATE_PIT_UNIVERSE_INTERVAL_TYPE,
        "feature_readiness_policy": CANDIDATE_FEATURE_READINESS_POLICY,
    }
    if promotion_gate_pass:
        release_manifest.setdefault("research_coverage", {})
        release_manifest["research_coverage"]["research_verified_start"] = published_research_start
        release_manifest["research_coverage"]["research_verified_end"] = published_research_end
        release_manifest["research_coverage"]["monthly_snapshot_start"] = published_research_monthly_start
        release_manifest["research_quality_intervals"] = research_quality_intervals
        release_manifest["git_commit"] = git_sha
        release_manifest["candidate_promotion_decisions"] = candidate_promotion_decisions
        release_manifest["earliest_candidate_gate_pass_start"] = earliest_candidate_gate_pass_start
        release_manifest["refined_earliest_candidate_gate_pass_boundary"] = refined_earliest_candidate_gate_pass_boundary
        release_manifest["candidate_recommended_research_interval"] = candidate_recommended_research_interval
        release_manifest["candidate_recommended_pit_universe_interval"] = candidate_recommended_pit_universe_interval
        (release / DATA_RELEASE_MANIFEST_ARTIFACT).write_text(
            json.dumps(release_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    executive_text = [
        "# Extended history research readiness",
        "",
        "This report answers whether the bounded liquid decision universe can move before the current 2013 control start.",
        "It is generated from release artifacts and companion audit reports. It does not promote an interval by prose.",
        "",
        "## Executive answers",
        "",
        f"1. Earliest official source date: `{observed_coverage.get('observed_start')}`.",
        f"2. Reliable pre-2006 history found: `{pre2006_available_text}` based on `{pre2006_valid}` valid representative probes out of `{len(pre2006_rows)}`.",
        f"3. Earliest 60-session readiness: `{feature_ready_dates.get('liquidity_60')}`.",
        f"4. Earliest 126-session readiness: `{feature_ready_dates.get('liquidity_rank_126')}`.",
        f"5. Earliest 252-session readiness: `{feature_ready_dates.get('standard_research_252')}`.",
        f"6. Earliest 272-session eligibility readiness: `{feature_ready_dates.get('liquid_v1_listing_age')}`.",
        f"7. Earliest 273-session momentum-style readiness: `{feature_ready_dates.get('momentum_12_1')}`.",
        f"8. Earliest fully warmed research date: `{earliest_fully_warmed}`.",
        "9. Years passing identity promotion: see `pre2013_research_identity_promotion.md` and `research_readiness_by_year.md`.",
        "10. Years failing promotion: see `research_readiness_by_year.md`.",
        "11. Early identities requiring intervention: see `pre2013_identity_priority.md` and `pre2013_identity_episode_audit.md`.",
        f"12. Required securities unresolved before `{CURRENT_PROVEN_RESEARCH_START_DATE}`: `{pre2013_identity_failures}` monthly required-scope identity failures.",
        f"13. Material corporate actions lacking factors in promoted required scope: `{missing_factor_count}`.",
        f"14. Left-censored material boundaries: `{left_boundary_events}`.",
        "15. Boundary contamination capability: see `pre2013_adjusted_return_quality.md`; only candidate lookback/signal-window non-PASS boundaries are promotion-relevant.",
        f"16. Price-return series trust: `{RECOMMENDED_SIGNAL_PRICE_SERIES}` is the promoted signal series when price-action candidate gates pass.",
        "17. Liquidity features session-correct: `session_correct_liquidity_audit.md` documents official-session windows.",
        "18. Survivorship protection: see `pre2013_survivorship_evidence.md` and `survivorship_audit.md`.",
        f"19. 2013+ v2.0.1 regression status: `{regression_status}`.",
        "20. RESEARCH_HIGH_CONFIDENCE intervals:",
        *research_interval_text,
        f"21. RESEARCH_EXPLORATORY intervals: any interval marked `{RESEARCH_EXPLORATORY_STATUS}` in `research_quality_intervals`, plus candidate intervals whose gates are not all pass.",
        f"22. SOURCE_ONLY interval: source observations before the first promoted research interval remain `{SOURCE_ONLY_STATUS}` or warmup-only evidence.",
        "23. Downstream Model Arena safe pre-2013 start: not declared by this report unless all hard gates plus CI/test evidence pass.",
        f"24. Earliest PIT-universe gate-pass start: `{earliest_pit_universe_gate_pass_start}`. Refined earliest PIT monthly/session boundary: `{refined_earliest_candidate_gate_pass_boundary}`. Earliest all-gates research candidate start: `{earliest_candidate_gate_pass_start}`. Candidate recommended PIT-universe interval: `{candidate_recommended_pit_universe_interval}`. This is not a final safe start unless full release evidence also passes.",
        "25. Remaining limitations: terminal values and total-return dividends remain partial; market cap and historical sector data are not fabricated.",
        "",
        "## Candidate gate matrix",
        "",
        "A missing candidate audit row is an explicit non-pass state.",
        *candidate_decision_text,
        "",
        "## Final promotion rule",
        "",
        "PIT membership interval: `SOURCE_INTEGRITY = PASS`, `SESSION_LIQUIDITY = PASS`, `RESEARCH_IDENTITY_FAILURES = 0`, `INSTRUMENT_SCOPE_FAILURES = 0`, `STATUS_GATE = PASS`, and `PIT_INVARIANTS = PASS`.",
        "",
        "Feature/model-ready research interval: the PIT membership interval gates must pass, `MATERIAL_PRICE_ACTION_MISSING_FACTORS = 0`, price-action boundary risk must be cleared for the promoted signal window, `WARMUP_READINESS = PASS` for the required published feature/model windows, `CI = PASS`, and regression evidence must pass or be fully justified. Do not remove otherwise valid universe securities only because a downstream model feature is not ready.",
        "",
        "Terminal values and complete total-return history are not required for price-return alpha research, but their limitations must remain explicit.",
    ]
    write(reports / "extended_history_research_readiness.md", "\n".join(executive_text))
    manifest = {
        "release_id": release.name,
        "git_sha": git_sha,
        "research_quality": {"status": quality, "start": published_research_start, "end": published_research_end, "monthly_snapshot_start": published_research_monthly_start, "universe_profile": PROFILE_ID, "profile_version": PROFILE_VERSION, "priority_scope": PRIORITY_SCOPE},
        "source_coverage": {
            "observed_start": observed_coverage.get("observed_start"),
            "observed_end": observed_coverage.get("observed_end"),
            "research_start": published_research_start,
            "research_end": published_research_end,
        },
        "warmup_coverage": {
            "feature_readiness_windows": warmup_coverage.get("feature_readiness_windows", FEATURE_READINESS_WINDOWS),
            "feature_ready_dates": warmup_coverage.get("feature_ready_dates", {}),
            "required_prior_sessions_for_full_readiness": warmup_coverage.get("required_prior_sessions_for_full_readiness"),
            "earliest_fully_warmed_date": warmup_coverage.get("earliest_fully_warmed_date"),
        },
        "research_quality_intervals": research_quality_intervals,
        "candidate_promotion_decisions": candidate_promotion_decisions,
        "earliest_pit_universe_gate_pass_start": earliest_pit_universe_gate_pass_start,
        "earliest_candidate_gate_pass_start": earliest_candidate_gate_pass_start,
        "refined_earliest_candidate_gate_pass_boundary": refined_earliest_candidate_gate_pass_boundary,
        "candidate_recommended_pit_universe_interval": candidate_recommended_pit_universe_interval,
        "candidate_recommended_research_interval": candidate_recommended_research_interval,
        "required_research_securities": int(promoted_required_count),
        "candidate_required_research_securities": int(required_count),
        "required_quality_threshold": REQUIRED_QUALITY_THRESHOLD,
        "recommended_signal_price_series": RECOMMENDED_SIGNAL_PRICE_SERIES,
        "raw_execution_price_artifact": RAW_EXECUTION_PRICE_ARTIFACT,
        "liquidity_artifact": LIQUIDITY_ARTIFACT,
        "top_liquidity_ranking_metric": TOP_LIQUIDITY_RANKING_METRIC,
        "liquid_v1_definition": LIQUID_V1_DEFINITION,
        "terminal_value_policy_requirement": TERMINAL_VALUE_POLICY_REQUIREMENT,
        "liquid_v1_securities": int(promoted_liquid_count),
        "candidate_liquid_v1_securities": int(counts[3]),
        "identity_failures": int(required_scope_failure_count),
        "material_price_action_missing_factors": missing_factor_count,
        "material_price_action_unresolved_boundaries": int(unresolved_boundary_count),
        "boundary_validation": dict(boundary_rows),
        "status_interval_overlaps": int(status_overlap),
        "research_invariant_validation_sha256": sha256(validation_path) if validation_path.exists() else None,
        "candidate_promotion_audit_sha256": sha256(candidate_promotion_audit_path) if candidate_promotion_audit_path.exists() else None,
        "test_result_sha256": sha256(test_result_path) if test_result_path.exists() else None,
        "ci_status_sha256": sha256(ci_status_path) if ci_status_path.exists() else None,
        "partitioned_artifacts_manifest_sha256": sha256(partition_manifest_path) if partition_manifest_path.exists() else None,
        "artifacts": {name: sha256(release / name) for name in RESEARCH_MANIFEST_ARTIFACTS},
        "research_universe_monthly_contract": [
            "date",
            "security_id",
            "listing_episode_id",
            "symbol_at_date",
            "instrument_type",
            "identity_quality",
            "known_listing_date",
            "listing_date_quality",
            "observed_history_start",
            "listing_age_sessions_quality",
            "listing_history_left_censored",
            "price",
            "history_sessions",
            "positive_volume_days_60",
            "median_traded_value_60",
            "median_traded_value_126",
            "liquidity_rank_126",
            "liquidity_percentile",
            "LIQUID_V1_eligible",
            "NSE_BROAD_LIQUID_PIT_V1_eligible",
            "top500_liquidity",
            "top750_liquidity",
            "top1000_liquidity",
            "research_identity_ok",
            "price_adjustment_quality",
            "price_adjustment_ok",
            "status_quality",
            "feature_ready_60",
            "feature_ready_126",
            "signal_history_ready_252",
            "signal_history_ready_273",
            "model_handoff_history_ready_300",
            "feature_readiness_source",
            "profile_id",
            "profile_version",
            "as_of_date",
            "eligibility_result",
            "eligibility_reason_codes",
        ],
        "required_research_security_contract": [
            "security_id",
            "first_research_date",
            "last_research_date",
            "enters_liquid_v1",
            "enters_top750",
            "best_rank_126",
            "worst_rank_126",
            "max_median_traded_value_60",
            "max_median_traded_value_126",
            "max_positive_volume_days_60",
            "research_identity_quality",
            "price_adjustment_quality",
            "price_adjustment_ok",
            "instrument_type",
            "instrument_type_quality",
            "status_quality",
            "active_trading_ok",
        ],
        "config_sha256": sha256(Path(args.config)),
        "manual_override_sha256": sha256(Path(args.manual_overrides)),
        "quality_reports": {name: sha256(reports / name) for name in REQUIRED_RESEARCH_REPORTS},
        "known_policy": {"signals": SIGNAL_POLICY, "execution": EXECUTION_POLICY, "terminal_values": TERMINAL_VALUE_POLICY},
        "known_limitations": [
            "Complete 2006 onward archive remains dataset-wide exploratory outside the scoped research universe.",
            "Terminal-event, merger, insolvency, and terminal-value history is partial; unresolved values require downstream recovery sensitivity.",
            "Cash-dividend and total-return coverage is partial and separately quality-labelled.",
            "Historical PIT market-cap and sector datasets are not fabricated in this release.",
            "Historical source retrieval timestamps may reflect local raw-file metadata where original HTTP retrieval metadata is unavailable.",
        ],
    }
    (release / RESEARCH_RELEASE_MANIFEST_ARTIFACT).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"quality": quality, "liquid_v1": int(promoted_liquid_count), "required": int(promoted_required_count), "candidate_required": int(required_count), "identity_failures": int(required_scope_failure_count), "missing_price_action_factors": missing_factor_count}, sort_keys=True))


if __name__ == "__main__":
    main()
