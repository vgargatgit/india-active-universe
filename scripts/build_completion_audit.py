#!/usr/bin/env python3
"""Generate a requirement-level audit for a published Parquet release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb


REQUIRED = [
    "security_master.parquet", "symbol_history.parquet", "issuer_master.parquet",
    "listing_episodes.parquet", "daily_prices_raw.parquet", "daily_prices_adjusted.parquet",
    "corporate_actions.parquet", "trading_status.parquet", "active_universe_daily.parquet",
    "liquidity_features.parquet", "terminal_events.parquet", "data_release_manifest.json",
    "trading_calendar.parquet",
    "company_name_history.parquet", "isin_history.parquet",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    release = Path(args.release)
    manifest = json.loads((release / "data_release_manifest.json").read_text(encoding="utf-8"))
    con = duckdb.connect()

    def count(name: str, where: str = "") -> int:
        sql = "SELECT count(*) FROM read_parquet(?)" + (f" WHERE {where}" if where else "")
        return con.execute(sql, [str(release / name)]).fetchone()[0]

    status_path = release / "trading_status_intervals.parquet"
    overlap_count = None
    suspended_count = None
    if status_path.exists():
        overlap_count = con.execute(
            """WITH ordered AS (
                SELECT *, lag(status_end) OVER (PARTITION BY security_id ORDER BY status_start) AS prior_end
                FROM read_parquet(?)
            ) SELECT count(*) FROM ordered
            WHERE prior_end IS NOT NULL AND status_start <= prior_end""",
            [str(status_path)],
        ).fetchone()[0]
        suspended_count = count("trading_status_intervals.parquet", "trading_status = 'SUSPENDED'")

    quality = {}
    adjusted = release / "daily_prices_adjusted.parquet"
    if adjusted.exists():
        quality = dict(con.execute("SELECT total_return_quality, count(*) FROM read_parquet(?) GROUP BY 1", [str(adjusted)]).fetchall())
    boundary_path = release / "corporate_action_boundary_validation.parquet"
    boundary_quality = {}
    if boundary_path.exists():
        boundary_quality = dict(con.execute("SELECT validation_status, count(*) FROM read_parquet(?) GROUP BY 1", [str(boundary_path)]).fetchall())

    rows = [
        f"# Release completion audit: `{manifest['release_id']}`",
        "",
        "## Proven facts",
        "",
        f"- Coverage: `{manifest.get('coverage', {}).get('observed_start')}` through `{manifest.get('coverage', {}).get('observed_end')}`.",
        f"- Official daily observations: {count('daily_prices_raw.parquet'):,}.",
        f"- Canonical security-master rows: {count('security_master.parquet'):,}.",
        f"- Issuers: {count('issuer_master.parquet'):,}.",
        f"- Listing episodes: {count('listing_episodes.parquet'):,}.",
        f"- Corporate-action rows: {count('corporate_actions.parquet'):,}.",
        f"- Terminal-event rows: {count('terminal_events.parquet'):,}.",
        f"- Status intervals: {count('trading_status_intervals.parquet') if status_path.exists() else 'not published':,}." if status_path.exists() else "- Status intervals: not published.",
        f"- Suspended intervals: {suspended_count:,}." if suspended_count is not None else "- Suspended intervals: not measured.",
        f"- Status interval overlaps: {overlap_count:,}." if overlap_count is not None else "- Status interval overlaps: not measured.",
        f"- Adjusted-price quality counts: `{quality}`.",
        f"- Corporate-action boundary validation: `{boundary_quality}`." if boundary_path.exists() else "- Corporate-action boundary validation: not published.",
        "",
        "## Required artifact checks",
        "",
    ]
    for name in REQUIRED:
        rows.append(f"- {'PASS' if (release / name).exists() else 'FAIL'}: `{name}`")
    rows += [
        "",
        "## Explicit limitations",
        "",
        "- The release is exploratory, not confirmatory-ready.",
        "- Scanned delisting notices require external OCR tooling and remain evidence-only.",
        "- Many terminal-event identities, merger events, insolvency outcomes, and terminal values remain unresolved.",
        "- Cash-dividend and total-return adjustment coverage is partial.",
        "- Historical sector and market-cap PIT data are not fabricated.",
        "",
    ]
    Path(args.out).write_text("\n".join(rows), encoding="utf-8")
    print(f"WROTE {args.out}")


if __name__ == "__main__":
    main()
