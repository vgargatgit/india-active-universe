#!/usr/bin/env python3
"""Generate a requirement-level audit for a published Parquet release."""

from __future__ import annotations

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import duckdb


REQUIRED = [
    "security_master.parquet", "symbol_history.parquet", "issuer_master.parquet",
    "listing_episodes.parquet", "daily_prices_raw.parquet", "daily_prices_adjusted.parquet",
    "corporate_actions.parquet", "trading_status.parquet", "trading_status_intervals.parquet", "suspension_events_resolved.parquet", "active_universe_daily.parquet",
    "liquidity_features.parquet", "terminal_events.parquet", "data_release_manifest.json",
    "trading_calendar.parquet",
    "company_name_history.parquet", "isin_history.parquet", "corporate_action_boundary_validation.parquet",
    "research_universe_monthly.parquet", "required_research_security.parquet",
    "research_release_manifest.json",
]

REQUIRED_RESEARCH_REPORTS = [
    "data_source_coverage.md", "research_universe_coverage.md", "research_identity_priority.md", "research_identity_promotion.md",
    "research_price_adjustment_promotion.md", "research_universe_corporate_action_audit.md",
    "session_correct_liquidity_audit.md", "research_universe_stability.md", "survivorship_audit.md",
    "current_survivor_comparison.md", "research_scale.md",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def junit_summary(path: Path) -> dict:
    root = ET.parse(path).getroot()
    suites = list(root.iter("testsuite"))
    tests = sum(int(suite.get("tests", "0")) for suite in suites)
    failures = sum(int(suite.get("failures", "0")) for suite in suites)
    errors = sum(int(suite.get("errors", "0")) for suite in suites)
    skipped = sum(int(suite.get("skipped", "0")) for suite in suites)
    handoff_cases = [
        case for case in root.iter("testcase")
        if case.get("classname") == "tests.test_model_arena_handoff"
        and case.get("name") == "test_model_arena_handoff_reads_profile_history_liquidity_and_execution_prices"
    ]
    handoff_passed = bool(handoff_cases) and all(case.find("skipped") is None for case in handoff_cases)
    return {
        "tests": tests,
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
        "model_arena_handoff_passed": handoff_passed,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    release = Path(args.release)
    report_dir = Path(args.out).resolve().parent
    manifest = json.loads((release / "data_release_manifest.json").read_text(encoding="utf-8"))
    research_manifest_path = release / "research_release_manifest.json"
    research_manifest = json.loads(research_manifest_path.read_text(encoding="utf-8")) if research_manifest_path.exists() else {}
    missing = [name for name in REQUIRED if not (release / name).exists()]
    missing_reports = [name for name in REQUIRED_RESEARCH_REPORTS if not (report_dir / name).exists()]
    validation_report = report_dir / f"research_invariant_validation_{release.name}.json"
    if not validation_report.exists():
        missing_reports.append(validation_report.name)
    test_result_report = report_dir / f"test_results_{release.name}.xml"
    if not test_result_report.exists():
        missing_reports.append(test_result_report.name)
    manifest_mismatch = manifest.get("release_id") != release.name
    research_quality_ok = research_manifest.get("research_quality", {}).get("status") == "RESEARCH_HIGH_CONFIDENCE"
    if missing or missing_reports or manifest_mismatch or not research_quality_ok:
        rows = [f"# Release completion audit: `{manifest.get('release_id')}`", "", "## Required artifact checks", ""]
        rows.extend(f"- {'PASS' if name not in missing else 'FAIL'}: `{name}`" for name in REQUIRED)
        if manifest_mismatch:
            rows.extend(["", f"- FAIL: manifest release_id does not match directory `{release.name}`"])
        if not research_quality_ok:
            rows.extend(["", "- FAIL: research quality is not RESEARCH_HIGH_CONFIDENCE"])
        rows.extend(f"- FAIL: missing research report `{name}`" for name in missing_reports)
        Path(args.out).write_text("\n".join(rows) + "\n", encoding="utf-8")
        print(f"WROTE {args.out}")
        print("RELEASE_AUDIT_FAILED")
        raise SystemExit(1)
    hash_mismatches = []
    for key, expected in manifest.get("artifacts", {}).items():
        if not key.startswith("release/"):
            continue
        path = release / key.removeprefix("release/")
        if path.is_file() and sha256(path) != expected:
            hash_mismatches.append(key)
    for name, expected in research_manifest.get("artifacts", {}).items():
        path = release / name
        if not path.is_file() or sha256(path) != expected:
            hash_mismatches.append(f"research/{name}")
    for name, expected in research_manifest.get("quality_reports", {}).items():
        path = report_dir / name
        if not path.is_file() or sha256(path) != expected:
            hash_mismatches.append(f"report/{name}")
    validation_expected = research_manifest.get("research_invariant_validation_sha256")
    validation_path = report_dir / f"research_invariant_validation_{release.name}.json"
    if validation_expected and (not validation_path.is_file() or sha256(validation_path) != validation_expected):
        hash_mismatches.append(f"report/{validation_path.name}")
    test_expected = research_manifest.get("test_result_sha256")
    if test_expected and (not test_result_report.is_file() or sha256(test_result_report) != test_expected):
        hash_mismatches.append(f"report/{test_result_report.name}")
    if hash_mismatches:
        rows = [f"# Release completion audit: `{manifest.get('release_id')}`", "", "## Artifact hash checks", ""]
        rows.extend(f"- FAIL: `{key}`" if key in hash_mismatches else f"- PASS: `{key}`" for key in sorted(manifest.get("artifacts", {})))
        Path(args.out).write_text("\n".join(rows) + "\n", encoding="utf-8")
        print(f"WROTE {args.out}")
        print("RELEASE_AUDIT_FAILED")
        for key in hash_mismatches:
            print(f"- artifact hash mismatch: {key}")
        raise SystemExit(1)
    test_summary = junit_summary(test_result_report)
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
        f"- Adjusted-price quality counts: `{json.dumps(quality, sort_keys=True)}`.",
        f"- Corporate-action boundary validation: `{json.dumps(boundary_quality, sort_keys=True)}`." if boundary_path.exists() else "- Corporate-action boundary validation: not published.",
        f"- Test results: `{json.dumps(test_summary, sort_keys=True)}`.",
        "",
        "## Required artifact checks",
        "",
    ]
    failures = []
    if manifest.get("release_id") != release.name:
        failures.append(f"manifest release_id {manifest.get('release_id')!r} does not match directory {release.name!r}")
    if not research_quality_ok:
        failures.append("research release is not RESEARCH_HIGH_CONFIDENCE")
    failures.extend(f"missing required research report: {name}" for name in missing_reports)
    if test_summary["tests"] <= 0 or test_summary["failures"] or test_summary["errors"]:
        failures.append(f"test result report is not clean: {json.dumps(test_summary, sort_keys=True)}")
    if not test_summary["model_arena_handoff_passed"]:
        failures.append("Model Arena handoff smoke test did not pass in release evidence")
    for name in REQUIRED:
        present = (release / name).exists()
        rows.append(f"- {'PASS' if present else 'FAIL'}: `{name}`")
        if not present:
            failures.append(f"missing required artifact: {name}")
    rows += [
        "",
        "## Explicit limitations",
        "",
        "- The complete 2006 onward archive is exploratory; the scoped 2013 onward research universe is RESEARCH_HIGH_CONFIDENCE.",
        "- Scanned delisting notices require external OCR tooling and remain evidence-only.",
        "- Many terminal-event identities, merger events, insolvency outcomes, and terminal values remain unresolved.",
        "- Cash-dividend and total-return adjustment coverage is partial.",
        "- Historical sector and market-cap PIT data are not fabricated.",
        "",
    ]
    Path(args.out).write_text("\n".join(rows), encoding="utf-8")
    print(f"WROTE {args.out}")
    if failures:
        print("RELEASE_AUDIT_FAILED")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
