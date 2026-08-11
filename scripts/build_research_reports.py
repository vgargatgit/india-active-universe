#!/usr/bin/env python3
"""Create scoped Phase 2 reports and the downstream research manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import duckdb


MATERIAL_ACTIONS = "('SPLIT', 'REVERSE_SPLIT', 'BONUS')"


def path_sql(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def scalar(connection: duckdb.DuckDBPyConnection, query: str):
    return connection.execute(query).fetchone()[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--reports", default="reports")
    parser.add_argument("--config", default="config/default.yaml")
    parser.add_argument("--manual-overrides", default="data/reference/manual_identity_overrides.yaml")
    args = parser.parse_args()
    release = Path(args.release)
    reports = Path(args.reports)
    r = path_sql(release)
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
          WHERE NSE_BROAD_LIQUID_PIT_V1_eligible OR top750_liquidity
          GROUP BY 1 ORDER BY 1
        """).fetchall()
        adjustment_rows = connection.execute(f"""
          SELECT adjustment_quality, COUNT(*)
          FROM read_parquet('{r}/daily_prices_adjusted.parquet') p
          JOIN read_parquet('{r}/required_research_security.parquet') q USING (security_id)
          GROUP BY 1 ORDER BY 1
        """).fetchall()
        event_rows = connection.execute(f"""
          SELECT ca.event_type, COUNT(*) AS events,
            COUNT(*) FILTER (WHERE ca.price_factor IS NULL OR ca.share_factor IS NULL) AS missing_factors
          FROM read_parquet('{r}/corporate_actions.parquet') ca
          JOIN read_parquet('{r}/required_research_security.parquet') q USING (security_id)
          WHERE ca.event_type IN {MATERIAL_ACTIONS}
          GROUP BY 1 ORDER BY 1
        """).fetchall()
        event_detail_rows = connection.execute(f"""
          SELECT ca.security_id, ca.symbol_at_event, ca.event_date, ca.event_type,
            ca.price_factor, ca.share_factor, v.pre_event_close, v.post_event_close,
            CASE WHEN v.pre_event_close IS NOT NULL AND v.pre_event_close <> 0 AND v.post_event_close IS NOT NULL
              THEN v.post_event_close / v.pre_event_close - 1 END AS raw_boundary_return,
            CASE WHEN v.pre_event_close IS NOT NULL AND v.pre_event_close <> 0 AND v.post_event_close IS NOT NULL AND ca.price_factor IS NOT NULL AND ca.price_factor <> 0
              THEN v.post_event_close / (v.pre_event_close * ca.price_factor) - 1 END AS adjusted_boundary_return,
            v.holder_value_ratio, v.validation_status
          FROM read_parquet('{r}/corporate_actions.parquet') ca
          JOIN read_parquet('{r}/required_research_security.parquet') q USING (security_id)
          LEFT JOIN read_parquet('{r}/corporate_action_boundary_validation.parquet') v
            ON v.event_id = ca.event_id
          WHERE ca.event_type IN {MATERIAL_ACTIONS}
          ORDER BY CAST(ca.event_date AS DATE), ca.security_id
        """).fetchall()
        boundary_rows = connection.execute(f"""
          SELECT v.validation_status, COUNT(DISTINCT v.event_id)
          FROM read_parquet('{r}/corporate_action_boundary_validation.parquet') v
          JOIN read_parquet('{r}/required_research_security.parquet') q USING (security_id)
          WHERE CAST(v.ex_date AS DATE) >= DATE '2013-01-01'
          GROUP BY 1 ORDER BY 1
        """).fetchall()
        status_overlap = scalar(connection, f"""
          SELECT COUNT(*) FROM (
            SELECT security_id, status_start,
              LAG(status_end) OVER (PARTITION BY security_id ORDER BY status_start) AS previous_end
            FROM read_parquet('{r}/trading_status_intervals.parquet')
          ) WHERE previous_end IS NOT NULL AND status_start <= previous_end
        """)
        max_absent = scalar(connection, f"SELECT COALESCE(MAX(absent_observation_days_60), 0) FROM read_parquet('{r}/research_universe_monthly.parquet')")
        required_count = scalar(connection, f"SELECT COUNT(*) FROM read_parquet('{r}/required_research_security.parquet')")
        coverage = connection.execute(f"SELECT MIN(date), MAX(date) FROM read_parquet('{r}/research_universe_monthly.parquet')").fetchone()
        monthly_detail_rows = connection.execute(f"""
          SELECT date, security_id, NSE_BROAD_LIQUID_PIT_V1_eligible, top750_liquidity,
                 top500_liquidity, top1000_liquidity
          FROM read_parquet('{r}/research_universe_monthly.parquet')
        """).fetchall()
        identity_priority_rows = connection.execute(f"""
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
            MAX(CASE WHEN u.research_identity_ok THEN 1 ELSE 0 END)::BOOLEAN AS research_identity_ok
          FROM read_parquet('{r}/required_research_security.parquet') q
          JOIN read_parquet('{r}/security_master.parquet') m USING (security_id)
          LEFT JOIN read_parquet('{r}/research_universe_monthly.parquet') u USING (security_id)
          GROUP BY q.security_id
          ORDER BY max_liquidity_rank_126 NULLS LAST, q.security_id
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
          WHERE l.last_observed_date < DATE '2026-08-10'
          ORDER BY e.last_eligible_date DESC, e.security_id
          LIMIT 25
        """).fetchall()
        disappeared_count = scalar(connection, f"""
          SELECT COUNT(*) FROM (
            SELECT security_id, MAX(CAST(date AS DATE)) AS last_observed
            FROM read_parquet('{r}/daily_prices_raw.parquet') GROUP BY security_id
          ) WHERE last_observed < DATE '2026-08-10'
        """)
        current_survivor_eligible = scalar(connection, f"""
          SELECT COUNT(DISTINCT u.security_id)
          FROM read_parquet('{r}/research_universe_monthly.parquet') u
          JOIN (SELECT security_id, MAX(CAST(date AS DATE)) AS last_seen FROM read_parquet('{r}/daily_prices_raw.parquet') GROUP BY security_id) l USING (security_id)
          WHERE u.NSE_BROAD_LIQUID_PIT_V1_eligible AND l.last_seen = DATE '2026-08-10'
        """)
        historical_eligible = scalar(connection, f"SELECT COUNT(DISTINCT security_id) FROM read_parquet('{r}/research_universe_monthly.parquet') WHERE NSE_BROAD_LIQUID_PIT_V1_eligible")
        required_scope_failure_count = scalar(connection, f"""
          SELECT COUNT(DISTINCT security_id)
          FROM read_parquet('{r}/research_universe_monthly.parquet')
          WHERE (NSE_BROAD_LIQUID_PIT_V1_eligible OR top750_liquidity)
            AND NOT research_identity_ok
        """)
        yearly_required_rows = connection.execute(f"""
          SELECT EXTRACT(YEAR FROM date)::INTEGER AS year,
            COUNT(DISTINCT security_id) FILTER (WHERE top750_liquidity OR NSE_BROAD_LIQUID_PIT_V1_eligible) AS required_count,
            COUNT(DISTINCT security_id) FILTER (WHERE (top750_liquidity OR NSE_BROAD_LIQUID_PIT_V1_eligible) AND research_identity_ok) AS identity_passing,
            COUNT(DISTINCT security_id) FILTER (WHERE (top750_liQUIDITY OR NSE_BROAD_LIQUID_PIT_V1_eligible) AND NOT research_identity_ok) AS identity_failures,
            COUNT(DISTINCT security_id) FILTER (WHERE (top750_liquidity OR NSE_BROAD_LIQUID_PIT_V1_eligible) AND NOT price_adjustment_ok) AS price_action_failures,
            COUNT(DISTINCT security_id) FILTER (WHERE (top750_liquidity OR NSE_BROAD_LIQUID_PIT_V1_eligible) AND status_quality = 'UNKNOWN_STATUS') AS unknown_status_exclusions
          FROM read_parquet('{r}/research_universe_monthly.parquet')
          GROUP BY 1 ORDER BY 1
        """).fetchall()
        terminal_sensitivity_count = scalar(connection, f"""
          SELECT COUNT(DISTINCT q.security_id)
          FROM read_parquet('{r}/required_research_security.parquet') q
          JOIN read_parquet('{r}/terminal_events.parquet') t USING (security_id)
          WHERE t.terminal_value IS NULL OR t.terminal_value_quality IN ('UNKNOWN', 'UNRESOLVED')
        """)
    finally:
        connection.close()

    identity_failure_count = int(counts[5])
    missing_factor_count = sum(int(row[2]) for row in event_rows)
    gate_pass = int(required_scope_failure_count) == 0 and missing_factor_count == 0 and int(status_overlap) == 0
    quality = "RESEARCH_HIGH_CONFIDENCE" if gate_pass else "RESEARCH_EXPLORATORY"
    research_start = "2013-01-01"
    git_sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    validation_path = reports / f"research_invariant_validation_{release.name}.json"
    test_result_path = reports / f"test_results_{release.name}.xml"
    ci_status_path = reports / f"ci_status_{release.name}.json"
    partition_manifest_path = release / "partitioned_artifacts_manifest.json"

    year_map = {int(row[0]): row[1:] for row in yearly_required_rows}
    year_text = ["| Year | Active ordinary | LIQUID_V1 | Top-750 | Required | Identity passing | Identity failures | Price-action failures | Unknown-status exclusions | Sparse names |", "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for y, a, l, t, _old_i, s in year_rows:
        required, passing, failures, price_failures, unknown_status = year_map[int(y)]
        year_text.append(f"| {int(y)} | {a} | {l} | {t} | {required} | {passing} | {failures} | {price_failures} | {unknown_status} | {s} |")
    write(reports / "research_universe_coverage.md", f"""# Research universe coverage

Profile: `NSE_BROAD_LIQUID_PIT_V1` / `LIQUID_V1`

Coverage: `{coverage[0]}` through `{coverage[1]}`.

Required research securities: `{required_count}` total (`{counts[3]}` LIQUID_V1 names and `{counts[4]}` Top-750 names).

{chr(10).join(year_text)}

The Top-750 set is a PIT liquidity diagnostic. It is not index membership.
""")
    identity_text = ["# Research identity promotion", "", f"Required research securities: `{required_count}`.", f"Identity failures in the full required scope: `{required_scope_failure_count}`.", "", "| Research identity quality | Securities |", "|---|---:|"]
    identity_text.extend(f"| `{quality_name}` | {number} |" for quality_name, number in identity_rows)
    identity_text.extend(["", "A `RECONSTRUCTED_TRADING_IDENTITY` is accepted when dated master rows resolve to one listing episode, one series, and no conflicting ISIN evidence. Multiple rows can represent symbol or name history within that episode.", f"Promotion gate: `{'PASS' if int(required_scope_failure_count) == 0 else 'FAIL'}`."])
    write(reports / "research_identity_promotion.md", "\n".join(identity_text))
    event_text = ["# Research universe corporate-action audit", "", "Material price actions are `SPLIT`, `REVERSE_SPLIT`, and `BONUS`.", "", "| Event type | Events | Missing factors |", "|---|---:|---:|"]
    event_text.extend(f"| `{kind}` | {events} | {missing} |" for kind, events, missing in event_rows)
    event_text.extend(["", f"Material events with missing price/share factors: `{missing_factor_count}`.", f"Promotion gate: `{'PASS' if missing_factor_count == 0 else 'FAIL'}`.", "", "## Boundary validation in the required scope", "", "| Boundary status | Distinct events |", "|---|---:|"])
    event_text.extend(f"| `{status}` | {number} |" for status, number in boundary_rows)
    event_text.extend(["", "## Material event details", "", "| Security | Symbol | Event date | Type | Price factor | Share factor | Pre close | Post close | Raw boundary return | Adjusted boundary return | Holder value ratio | Validation |", "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|"])
    event_text.extend(f"| `{sid}` | `{symbol}` | `{event_date}` | `{event_type}` | {price_factor} | {share_factor} | {pre_close} | {post_close} | {raw_return} | {adjusted_return} | {holder_ratio} | `{status}` |" for sid, symbol, event_date, event_type, price_factor, share_factor, pre_close, post_close, raw_return, adjusted_return, holder_ratio, status in event_detail_rows)
    event_text.extend(["", "`NO_PRE_EVENT_OBSERVATION` and `NO_POST_EVENT_OBSERVATION` identify listing-start or terminal-history edges. `NO_LOCAL_BOUNDARY_OBSERVATION` means the nearest price is more than five official sessions from the event. These cases do not create a false return and do not change the official factor or raw price. A local two-sided boundary is required before continuity is assessed.", "", "Rows remain traceable to `corporate_actions.parquet`; this report does not alter raw nominal prices."])
    write(reports / "research_universe_corporate_action_audit.md", "\n".join(event_text))
    adjustment_text = ["# Research price-adjustment promotion", "", "The recommended signal series is the price-return adjusted close. Raw nominal prices remain the execution series.", "", "| Adjustment quality | Rows |", "|---|---:|"]
    adjustment_text.extend(f"| `{kind}` | {number} |" for kind, number in adjustment_rows)
    adjustment_text.extend(["", f"Material-event factor gate: `{'PASS' if missing_factor_count == 0 else 'FAIL'}`.", "Total-return adjustment is separate and remains partial unless its own quality says otherwise."])
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
    identity_priority_text = ["# Research identity priority queue", "", "One row is included for every required research security.", "", "| Security | Symbol | Company | First seen | Last seen | Max rank | Liquid dates | Identity quality | ISIN evidence | Name count | Ticker count | Max absent 60d | Recommendation |", "|---|---|---|---|---|---:|---:|---|---|---:|---:|---:|---|"]
    for row in identity_priority_rows:
        sid, symbol, company, first_seen, last_seen, max_rank, liquid_dates, identity_quality, isin_evidence, name_count, symbol_count, max_absent_days, identity_ok = row
        recommendation = "ACCEPT_RESEARCH_IDENTITY" if identity_ok else "REVIEW_REQUIRED"
        identity_priority_text.append(f"| `{sid}` | `{symbol}` | `{company}` | `{first_seen}` | `{last_seen}` | {max_rank} | {liquid_dates} | `{identity_quality}` | `{isin_evidence or ''}` | {name_count} | {symbol_count} | {max_absent_days} | `{recommendation}` |")
    write(reports / "research_identity_priority.md", "\n".join(identity_priority_text))
    dates = sorted({row[0] for row in monthly_detail_rows})
    by_date = {point: {row[1] for row in monthly_detail_rows if row[0] == point and row[2]} for point in dates}
    top750_by_date = {point: {row[1] for row in monthly_detail_rows if row[0] == point and row[3]} for point in dates}
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
    manifest = {
        "release_id": release.name,
        "git_sha": git_sha,
        "research_quality": {"status": quality, "start": research_start, "end": str(coverage[1]), "monthly_snapshot_start": str(coverage[0]), "universe_profile": "NSE_BROAD_LIQUID_PIT_V1", "profile_version": "LIQUID_V1", "priority_scope": "LIQUID_V1_OR_HISTORICAL_TOP750"},
        "source_coverage": {"observed_start": "2006-01-02", "observed_end": "2026-08-10", "research_start": research_start, "research_end": str(coverage[1])},
        "required_research_securities": int(required_count),
        "liquid_v1_securities": int(counts[3]),
        "identity_failures": int(required_scope_failure_count),
        "material_price_action_missing_factors": missing_factor_count,
        "boundary_validation": dict(boundary_rows),
        "status_interval_overlaps": int(status_overlap),
        "research_invariant_validation_sha256": sha256(validation_path) if validation_path.exists() else None,
        "test_result_sha256": sha256(test_result_path) if test_result_path.exists() else None,
        "ci_status_sha256": sha256(ci_status_path) if ci_status_path.exists() else None,
        "partitioned_artifacts_manifest_sha256": sha256(partition_manifest_path) if partition_manifest_path.exists() else None,
        "artifacts": {name: sha256(release / name) for name in ("research_universe_monthly.parquet", "required_research_security.parquet", "liquidity_features.parquet", "daily_prices_raw.parquet", "daily_prices_adjusted.parquet", "corporate_actions.parquet", "corporate_action_boundary_validation.parquet", "trading_status_intervals.parquet", "suspension_events_resolved.parquet")},
        "config_sha256": sha256(Path(args.config)),
        "manual_override_sha256": sha256(Path(args.manual_overrides)),
        "quality_reports": {name: sha256(reports / name) for name in ("data_source_coverage.md", "research_universe_coverage.md", "research_identity_priority.md", "research_identity_promotion.md", "research_price_adjustment_promotion.md", "research_universe_corporate_action_audit.md", "session_correct_liquidity_audit.md", "research_universe_stability.md", "survivorship_audit.md", "current_survivor_comparison.md", "research_scale.md")},
        "known_policy": {"signals": "price-return adjusted close", "execution": "raw nominal OHLC", "terminal_values": "explicit recovery scenarios; no invented canonical value"},
    }
    (release / "research_release_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"quality": quality, "liquid_v1": counts[3], "required": required_count, "identity_failures": int(required_scope_failure_count), "missing_price_action_factors": missing_factor_count}, sort_keys=True))


if __name__ == "__main__":
    main()
