#!/usr/bin/env python3
"""Build candidate-start promotion audit metrics without changing release semantics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

from india_active_universe.profiles import (
    CANDIDATE_RESEARCH_START_DATES,
    FEATURE_READINESS_WINDOWS,
    LIQUID_V1_DEFINITION,
    PROFILE_ID,
    PROFILE_VERSION,
    PRIORITY_SCOPE,
    RESEARCH_START_DATE,
)


MATERIAL_ACTIONS = "('SPLIT', 'REVERSE_SPLIT', 'BONUS')"


def path_sql(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--control-start", default=RESEARCH_START_DATE)
    args = parser.parse_args()

    release = Path(args.release)
    r = path_sql(release)
    candidate_values = ", ".join(f"(DATE '{candidate}')" for candidate in CANDIDATE_RESEARCH_START_DATES)
    max_window = max(FEATURE_READINESS_WINDOWS.values())
    listing_age_min = LIQUID_V1_DEFINITION["listing_age_sessions_min"]

    connection = duckdb.connect()
    try:
        rows = connection.execute(f"""
          WITH candidates(candidate_start) AS (
            VALUES {candidate_values}
          ), candidate_sessions AS (
            SELECT c.candidate_start,
              MIN(cal.session_index) AS decision_session_index,
              MIN(CAST(cal.date AS DATE)) AS first_decision_session
            FROM candidates c
            LEFT JOIN read_parquet('{r}/trading_calendar.parquet') cal
              ON CAST(cal.date AS DATE) >= c.candidate_start
             AND CAST(cal.date AS DATE) < DATE '{args.control_start}'
            GROUP BY c.candidate_start
          ), candidate_expected_snapshots AS (
            SELECT candidate_start,
              MIN(month_end) AS first_expected_snapshot
            FROM (
              SELECT c.candidate_start,
                DATE_TRUNC('month', CAST(cal.date AS DATE)) AS month,
                MAX(CAST(cal.date AS DATE)) AS month_end
              FROM candidates c
              JOIN read_parquet('{r}/trading_calendar.parquet') cal
                ON CAST(cal.date AS DATE) >= c.candidate_start
               AND CAST(cal.date AS DATE) < DATE '{args.control_start}'
              GROUP BY c.candidate_start, DATE_TRUNC('month', CAST(cal.date AS DATE))
            )
            GROUP BY candidate_start
          ), scoped_monthly AS (
            SELECT c.candidate_start,
              u.*
            FROM candidates c
            LEFT JOIN read_parquet('{r}/research_universe_monthly.parquet') u
              ON CAST(u.date AS DATE) >= c.candidate_start
             AND CAST(u.date AS DATE) < DATE '{args.control_start}'
          ), required_scope AS (
            SELECT *
            FROM scoped_monthly
            WHERE security_id IS NOT NULL
              AND (NSE_BROAD_LIQUID_PIT_V1_eligible OR top750_liquidity)
          ), scoped_required_security AS (
            SELECT candidate_start,
              security_id,
              MIN(CAST(date AS DATE)) AS first_required_month,
              MAX(CAST(date AS DATE)) AS last_required_month,
              MIN(CASE WHEN research_identity_ok THEN 1 ELSE 0 END)::BOOLEAN AS identity_ok,
              MIN(CASE WHEN price_adjustment_ok THEN 1 ELSE 0 END)::BOOLEAN AS price_adjustment_ok,
              MIN(CASE WHEN instrument_type = 'ORDINARY_EQUITY'
                         AND instrument_type_quality IS NOT NULL
                         AND instrument_type_quality <> 'UNRESOLVED'
                       THEN 1 ELSE 0 END)::BOOLEAN AS instrument_ok,
              MIN(CASE WHEN status_quality NOT IN ('UNKNOWN_STATUS', 'UNRESOLVED')
                         AND status_quality IS NOT NULL
                       THEN 1 ELSE 0 END)::BOOLEAN AS status_ok
            FROM required_scope
            GROUP BY candidate_start, security_id
          ), material_events AS (
            SELECT sr.candidate_start,
              ca.event_id,
              ca.price_factor,
              ca.share_factor,
              COALESCE(v.validation_status, 'NO_BOUNDARY_VALIDATION') AS validation_status,
              cal.session_index AS event_session_index,
              cs.decision_session_index
            FROM scoped_required_security sr
            JOIN read_parquet('{r}/corporate_actions.parquet') ca USING (security_id)
            JOIN candidate_sessions cs USING (candidate_start)
            LEFT JOIN read_parquet('{r}/corporate_action_boundary_validation.parquet') v
              ON v.event_id = ca.event_id
            LEFT JOIN read_parquet('{r}/trading_calendar.parquet') cal
              ON CAST(cal.date AS DATE) = CAST(ca.event_date AS DATE)
            WHERE ca.event_type IN {MATERIAL_ACTIONS}
              AND CAST(ca.event_date AS DATE) < DATE '{args.control_start}'
              AND (
                CAST(ca.event_date AS DATE) >= sr.first_required_month
                OR cal.session_index >= cs.decision_session_index - {max_window}
              )
          ), month_counts AS (
            SELECT candidate_start,
              COUNT(*) AS monthly_rows,
              MIN(CAST(date AS DATE)) AS first_materialized_snapshot,
              COUNT(*) FILTER (WHERE model_handoff_history_ready_300) AS fully_warmed_rows,
              COUNT(*) FILTER (WHERE signal_history_ready_252) AS signal_ready_252_rows,
              COUNT(*) FILTER (WHERE signal_history_ready_273) AS signal_ready_273_rows,
              COUNT(DISTINCT date) AS monthly_snapshots,
              COUNT(DISTINCT date) FILTER (WHERE CAST(date AS DATE) >= cs.first_decision_session) AS monthly_snapshots_after_decision
            FROM scoped_monthly sm
            JOIN candidate_sessions cs USING (candidate_start)
            WHERE sm.security_id IS NOT NULL
            GROUP BY candidate_start
          ), required_counts AS (
            SELECT candidate_start,
              COUNT(*) AS required_rows,
              COUNT(*) FILTER (WHERE model_handoff_history_ready_300) AS fully_warmed_required_rows,
              COUNT(DISTINCT security_id) AS required_securities,
              COUNT(DISTINCT security_id) FILTER (WHERE identity_ok IS DISTINCT FROM TRUE) AS identity_failures,
              COUNT(DISTINCT security_id) FILTER (WHERE price_adjustment_ok IS DISTINCT FROM TRUE) AS price_adjustment_failures,
              COUNT(DISTINCT security_id) FILTER (WHERE instrument_ok IS DISTINCT FROM TRUE) AS instrument_failures,
              COUNT(DISTINCT security_id) FILTER (WHERE status_ok IS DISTINCT FROM TRUE) AS status_failures
            FROM scoped_required_security
            GROUP BY candidate_start
          ), material_counts AS (
            SELECT candidate_start,
              COUNT(DISTINCT event_id) AS material_events,
              COUNT(DISTINCT event_id) FILTER (WHERE price_factor IS NULL OR share_factor IS NULL) AS material_missing_factors,
              COUNT(DISTINCT event_id) FILTER (
                WHERE validation_status <> 'PASS'
                  AND event_session_index >= decision_session_index - {max_window}
              ) AS signal_window_non_pass_boundaries
            FROM material_events
            GROUP BY candidate_start
          ), liquidity_window_counts AS (
            SELECT rs.candidate_start,
              COUNT(*) FILTER (
                WHERE lf.liquidity_window_definition IS DISTINCT FROM 'OFFICIAL_NSE_SESSION_WINDOW'
              ) AS session_liquidity_window_failures
            FROM required_scope rs
            LEFT JOIN read_parquet('{r}/liquidity_features.parquet') lf
              ON lf.security_id = rs.security_id
             AND CAST(lf.date AS DATE) = CAST(rs.date AS DATE)
            GROUP BY rs.candidate_start
          ), candidate_boundaries AS (
            SELECT sm.candidate_start,
              CAST(sm.date AS DATE) AS boundary_date
            FROM scoped_monthly sm
            JOIN candidate_sessions cs USING (candidate_start)
            WHERE sm.security_id IS NOT NULL
              AND CAST(sm.date AS DATE) >= cs.first_decision_session
            GROUP BY sm.candidate_start, CAST(sm.date AS DATE)
          ), boundary_required_scope AS (
            SELECT cb.candidate_start,
              cb.boundary_date,
              CAST(rs.date AS DATE) AS date,
              rs.security_id,
              rs.research_identity_ok,
              rs.price_adjustment_ok,
              rs.instrument_type,
              rs.instrument_type_quality,
              rs.status_quality
            FROM candidate_boundaries cb
            JOIN required_scope rs
              ON rs.candidate_start = cb.candidate_start
             AND CAST(rs.date AS DATE) >= cb.boundary_date
          ), boundary_security_scope AS (
            SELECT candidate_start,
              boundary_date,
              security_id,
              MIN(CAST(date AS DATE)) AS first_required_month,
              MIN(CASE WHEN research_identity_ok THEN 1 ELSE 0 END)::BOOLEAN AS identity_ok,
              MIN(CASE WHEN price_adjustment_ok THEN 1 ELSE 0 END)::BOOLEAN AS price_adjustment_ok,
              MIN(CASE WHEN instrument_type = 'ORDINARY_EQUITY'
                         AND instrument_type_quality IS NOT NULL
                         AND instrument_type_quality <> 'UNRESOLVED'
                       THEN 1 ELSE 0 END)::BOOLEAN AS instrument_ok,
              MIN(CASE WHEN status_quality NOT IN ('UNKNOWN_STATUS', 'UNRESOLVED')
                         AND status_quality IS NOT NULL
                       THEN 1 ELSE 0 END)::BOOLEAN AS status_ok
            FROM boundary_required_scope
            GROUP BY candidate_start, boundary_date, security_id
          ), boundary_material_events AS (
            SELECT bss.candidate_start,
              bss.boundary_date,
              ca.event_id,
              ca.price_factor,
              ca.share_factor,
              COALESCE(v.validation_status, 'NO_BOUNDARY_VALIDATION') AS validation_status,
              event_cal.session_index AS event_session_index,
              boundary_cal.session_index AS boundary_session_index
            FROM boundary_security_scope bss
            JOIN read_parquet('{r}/corporate_actions.parquet') ca USING (security_id)
            LEFT JOIN read_parquet('{r}/corporate_action_boundary_validation.parquet') v
              ON v.event_id = ca.event_id
            LEFT JOIN read_parquet('{r}/trading_calendar.parquet') event_cal
              ON CAST(event_cal.date AS DATE) = CAST(ca.event_date AS DATE)
            LEFT JOIN read_parquet('{r}/trading_calendar.parquet') boundary_cal
              ON CAST(boundary_cal.date AS DATE) = bss.boundary_date
            WHERE ca.event_type IN {MATERIAL_ACTIONS}
              AND CAST(ca.event_date AS DATE) < DATE '{args.control_start}'
              AND (
                CAST(ca.event_date AS DATE) >= bss.first_required_month
                OR event_cal.session_index >= boundary_cal.session_index - {max_window}
              )
          ), boundary_material_counts AS (
            SELECT candidate_start,
              boundary_date,
              COUNT(DISTINCT event_id) FILTER (WHERE price_factor IS NULL OR share_factor IS NULL) AS material_missing_factors,
              COUNT(DISTINCT event_id) FILTER (
                WHERE validation_status <> 'PASS'
                  AND event_session_index >= boundary_session_index - {max_window}
              ) AS signal_window_non_pass_boundaries
            FROM boundary_material_events
            GROUP BY candidate_start, boundary_date
          ), boundary_gate_counts AS (
            SELECT brs.candidate_start,
              brs.boundary_date,
              COUNT(*) AS required_rows,
              COUNT(DISTINCT brs.security_id) AS required_securities,
              COUNT(DISTINCT brs.security_id) FILTER (WHERE bss.identity_ok IS DISTINCT FROM TRUE) AS identity_failures,
              COUNT(DISTINCT brs.security_id) FILTER (WHERE bss.price_adjustment_ok IS DISTINCT FROM TRUE) AS price_adjustment_failures,
              COUNT(DISTINCT brs.security_id) FILTER (WHERE bss.instrument_ok IS DISTINCT FROM TRUE) AS instrument_failures,
              COUNT(DISTINCT brs.security_id) FILTER (WHERE bss.status_ok IS DISTINCT FROM TRUE) AS status_failures,
              COUNT(*) FILTER (
                WHERE lf.liquidity_window_definition IS DISTINCT FROM 'OFFICIAL_NSE_SESSION_WINDOW'
              ) AS session_liquidity_window_failures,
              COALESCE(bmc.material_missing_factors, 0) AS material_missing_factors,
              COALESCE(bmc.signal_window_non_pass_boundaries, 0) AS signal_window_non_pass_boundaries
            FROM boundary_required_scope brs
            JOIN boundary_security_scope bss
              ON bss.candidate_start = brs.candidate_start
             AND bss.boundary_date = brs.boundary_date
             AND bss.security_id = brs.security_id
            LEFT JOIN read_parquet('{r}/liquidity_features.parquet') lf
              ON lf.security_id = brs.security_id
             AND CAST(lf.date AS DATE) = CAST(brs.date AS DATE)
            LEFT JOIN boundary_material_counts bmc
              ON bmc.candidate_start = brs.candidate_start
             AND bmc.boundary_date = brs.boundary_date
            GROUP BY brs.candidate_start, brs.boundary_date, bmc.material_missing_factors, bmc.signal_window_non_pass_boundaries
          ), refined_boundaries AS (
            SELECT candidate_start,
              MIN(boundary_date) AS refined_earliest_passing_snapshot
            FROM boundary_gate_counts
            WHERE required_rows > 0
              AND required_securities > 0
              AND identity_failures = 0
              AND price_adjustment_failures = 0
              AND instrument_failures = 0
              AND status_failures = 0
              AND session_liquidity_window_failures = 0
              AND material_missing_factors = 0
              AND signal_window_non_pass_boundaries = 0
            GROUP BY candidate_start
          )
          SELECT c.candidate_start,
            cs.first_decision_session,
            ces.first_expected_snapshot,
            mc.first_materialized_snapshot,
            rb.refined_earliest_passing_snapshot,
            COALESCE(mc.monthly_rows, 0) AS monthly_rows,
            COALESCE(mc.monthly_snapshots, 0) AS monthly_snapshots,
            COALESCE(mc.monthly_snapshots_after_decision, 0) AS monthly_snapshots_after_decision,
            COALESCE(mc.fully_warmed_rows, 0) AS fully_warmed_rows,
            COALESCE(mc.signal_ready_252_rows, 0) AS signal_ready_252_rows,
            COALESCE(mc.signal_ready_273_rows, 0) AS signal_ready_273_rows,
            COALESCE(rc.required_rows, 0) AS required_rows,
            COALESCE(rc.fully_warmed_required_rows, 0) AS fully_warmed_required_rows,
            COALESCE(rc.required_securities, 0) AS required_securities,
            COALESCE(rc.identity_failures, 0) AS identity_failures,
            COALESCE(rc.price_adjustment_failures, 0) AS price_adjustment_failures,
            COALESCE(rc.instrument_failures, 0) AS instrument_failures,
            COALESCE(rc.status_failures, 0) AS status_failures,
            COALESCE(mat.material_events, 0) AS material_events,
            COALESCE(mat.material_missing_factors, 0) AS material_missing_factors,
            COALESCE(mat.signal_window_non_pass_boundaries, 0) AS signal_window_non_pass_boundaries,
            COALESCE(lw.session_liquidity_window_failures, 0) AS session_liquidity_window_failures
          FROM candidates c
          LEFT JOIN candidate_sessions cs USING (candidate_start)
          LEFT JOIN candidate_expected_snapshots ces USING (candidate_start)
          LEFT JOIN month_counts mc USING (candidate_start)
          LEFT JOIN required_counts rc USING (candidate_start)
          LEFT JOIN material_counts mat USING (candidate_start)
          LEFT JOIN liquidity_window_counts lw USING (candidate_start)
          LEFT JOIN refined_boundaries rb USING (candidate_start)
          ORDER BY c.candidate_start DESC
        """).fetchall()
    finally:
        connection.close()

    audits = []
    for row in rows:
        (
            candidate_start,
            first_decision_session,
            first_expected_snapshot,
            first_materialized_snapshot,
            refined_earliest_passing_snapshot,
            monthly_rows,
            monthly_snapshots,
            monthly_snapshots_after_decision,
            fully_warmed_rows,
            signal_ready_252_rows,
            signal_ready_273_rows,
            required_rows,
            fully_warmed_required_rows,
            required_securities,
            identity_failures,
            price_adjustment_failures,
            instrument_failures,
            status_failures,
            material_events,
            material_missing_factors,
            signal_window_non_pass_boundaries,
            session_liquidity_window_failures,
        ) = row
        hard_failures = {
            "not_materialized": required_securities == 0 or monthly_snapshots == 0,
            "candidate_start_snapshot_missing": first_expected_snapshot is None or first_materialized_snapshot != first_expected_snapshot,
            "decision_window_snapshots_missing": first_decision_session is None or monthly_snapshots_after_decision == 0,
            "identity_failures": int(identity_failures),
            "price_adjustment_failures": int(price_adjustment_failures),
            "instrument_failures": int(instrument_failures),
            "status_failures": int(status_failures),
            "material_missing_factors": int(material_missing_factors),
            "signal_window_non_pass_boundaries": int(signal_window_non_pass_boundaries),
            "session_liquidity_window_failures": int(session_liquidity_window_failures),
        }
        feature_readiness = {
            "feature_warmup_not_ready": first_decision_session is None or required_rows == 0 or fully_warmed_required_rows < required_rows,
            "required_prior_sessions_for_full_readiness": max_window,
            "fully_warmed_required_rows": int(fully_warmed_required_rows),
            "required_rows": int(required_rows),
            "signal_ready_252_rows": int(signal_ready_252_rows),
            "signal_ready_273_rows": int(signal_ready_273_rows),
            "model_handoff_history_ready_300_rows": int(fully_warmed_required_rows),
        }
        status = "PASS" if (
            not hard_failures["not_materialized"]
            and not hard_failures["candidate_start_snapshot_missing"]
            and not hard_failures["decision_window_snapshots_missing"]
            and int(identity_failures) == 0
            and int(price_adjustment_failures) == 0
            and int(instrument_failures) == 0
            and int(status_failures) == 0
            and int(material_missing_factors) == 0
            and int(signal_window_non_pass_boundaries) == 0
            and int(session_liquidity_window_failures) == 0
        ) else "FAIL"
        audits.append({
            "candidate_start": str(candidate_start),
            "first_decision_session": str(first_decision_session) if first_decision_session else None,
            "first_expected_snapshot": str(first_expected_snapshot) if first_expected_snapshot else None,
            "first_materialized_snapshot": str(first_materialized_snapshot) if first_materialized_snapshot else None,
            "refined_earliest_passing_snapshot": str(refined_earliest_passing_snapshot) if refined_earliest_passing_snapshot else None,
            "control_start": args.control_start,
            "profile": PROFILE_ID,
            "profile_version": PROFILE_VERSION,
            "priority_scope": PRIORITY_SCOPE,
            "required_prior_sessions_for_full_readiness": max_window,
            "listing_age_sessions_min": listing_age_min,
            "monthly_rows": int(monthly_rows),
            "monthly_snapshots": int(monthly_snapshots),
            "monthly_snapshots_after_decision": int(monthly_snapshots_after_decision),
            "fully_warmed_rows": int(fully_warmed_rows),
            "signal_ready_252_rows": int(signal_ready_252_rows),
            "signal_ready_273_rows": int(signal_ready_273_rows),
            "required_rows": int(required_rows),
            "fully_warmed_required_rows": int(fully_warmed_required_rows),
            "required_securities": int(required_securities),
            "material_events": int(material_events),
            "feature_readiness": feature_readiness,
            "hard_failures": hard_failures,
            "status": status,
        })

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "release": release.name,
        "profile": PROFILE_ID,
        "profile_version": PROFILE_VERSION,
        "priority_scope": PRIORITY_SCOPE,
        "control_start": args.control_start,
        "candidate_start_dates": list(CANDIDATE_RESEARCH_START_DATES),
        "required_prior_sessions_for_full_readiness": max_window,
        "listing_age_sessions_min": listing_age_min,
        "candidate_audits": audits,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"release": release.name, "candidate_count": len(audits)}, sort_keys=True))


if __name__ == "__main__":
    main()
