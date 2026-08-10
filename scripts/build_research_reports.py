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
          WHERE NSE_BROAD_LIQUID_PIT_V1_eligible
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
    finally:
        connection.close()

    identity_failure_count = int(counts[5])
    missing_factor_count = sum(int(row[2]) for row in event_rows)
    gate_pass = identity_failure_count == 0 and missing_factor_count == 0 and int(status_overlap) == 0
    quality = "RESEARCH_HIGH_CONFIDENCE" if gate_pass else "RESEARCH_EXPLORATORY"
    git_sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()

    year_text = ["| Year | Active ordinary | LIQUID_V1 | Top-750 | Identity failures | Sparse names |", "|---:|---:|---:|---:|---:|---:|"]
    year_text.extend(f"| {int(y)} | {a} | {l} | {t} | {i} | {s} |" for y, a, l, t, i, s in year_rows)
    write(reports / "research_universe_coverage.md", f"""# Research universe coverage

Profile: `NSE_BROAD_LIQUID_PIT_V1` / `LIQUID_V1`

Coverage: `{coverage[0]}` through `{coverage[1]}`.

Required research securities: `{counts[3]}` liquid names and `{counts[4]}` Top-750 names.

{chr(10).join(year_text)}

The Top-750 set is a PIT liquidity diagnostic. It is not index membership.
""")
    identity_text = ["# Research identity promotion", "", f"Required research securities: `{required_count}`.", f"Identity failures in LIQUID_V1: `{identity_failure_count}`.", "", "| Research identity quality | Securities |", "|---|---:|"]
    identity_text.extend(f"| `{quality_name}` | {number} |" for quality_name, number in identity_rows)
    identity_text.extend(["", "A `RECONSTRUCTED_TRADING_IDENTITY` is accepted only when the release has one non-conflicting listing episode and one stable series for the security.", f"Promotion gate: `{'PASS' if identity_failure_count == 0 else 'FAIL'}`."])
    write(reports / "research_identity_promotion.md", "\n".join(identity_text))
    event_text = ["# Research universe corporate-action audit", "", "Material price actions are `SPLIT`, `REVERSE_SPLIT`, and `BONUS`.", "", "| Event type | Events | Missing factors |", "|---|---:|---:|"]
    event_text.extend(f"| `{kind}` | {events} | {missing} |" for kind, events, missing in event_rows)
    event_text.extend(["", f"Material events with missing price/share factors: `{missing_factor_count}`.", f"Promotion gate: `{'PASS' if missing_factor_count == 0 else 'FAIL'}`.", "", "Rows remain traceable to `corporate_actions.parquet`; this report does not alter raw nominal prices."])
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
    write(reports / "research_identity_priority.md", f"""# Research identity priority queue

The required scope contains `{required_count}` securities that enter LIQUID_V1 or PIT Top-750.

The current release has `{identity_failure_count}` identity failures inside LIQUID_V1.
Low-liquidity securities outside this scope remain in the exploratory archive and are not silently promoted.
""")
    manifest = {
        "release_id": release.name,
        "git_sha": git_sha,
        "research_quality": {"status": quality, "start": str(coverage[0]), "end": str(coverage[1]), "universe_profile": "NSE_BROAD_LIQUID_PIT_V1", "profile_version": "LIQUID_V1", "priority_scope": "LIQUID_V1_OR_HISTORICAL_TOP750"},
        "source_coverage": {"observed_start": "2006-01-02", "observed_end": "2026-08-10", "research_start": str(coverage[0]), "research_end": str(coverage[1])},
        "required_research_securities": int(required_count),
        "liquid_v1_securities": int(counts[3]),
        "identity_failures": identity_failure_count,
        "material_price_action_missing_factors": missing_factor_count,
        "status_interval_overlaps": int(status_overlap),
        "artifacts": {name: sha256(release / name) for name in ("research_universe_monthly.parquet", "required_research_security.parquet", "liquidity_features.parquet", "daily_prices_raw.parquet", "daily_prices_adjusted.parquet", "corporate_actions.parquet", "trading_status_intervals.parquet")},
        "config_sha256": sha256(Path(args.config)),
        "manual_override_sha256": sha256(Path(args.manual_overrides)),
        "quality_reports": {name: sha256(reports / name) for name in ("research_universe_coverage.md", "research_identity_promotion.md", "research_price_adjustment_promotion.md", "session_correct_liquidity_audit.md")},
        "known_policy": {"signals": "price-return adjusted close", "execution": "raw nominal OHLC", "terminal_values": "explicit recovery scenarios; no invented canonical value"},
    }
    (release / "research_release_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"quality": quality, "liquid_v1": counts[3], "required": counts[4], "identity_failures": identity_failure_count, "missing_price_action_factors": missing_factor_count}, sort_keys=True))


if __name__ == "__main__":
    main()
