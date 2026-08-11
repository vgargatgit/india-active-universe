#!/usr/bin/env python3
"""Generate a requirement-level audit for a published Parquet release."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import duckdb


REQUIRED = [
    "security_master.parquet", "symbol_history.parquet", "issuer_master.parquet",
    "listing_episodes.parquet", "daily_prices_raw.parquet", "daily_prices_adjusted.parquet",
    "corporate_actions.parquet", "trading_status.parquet", "trading_status_intervals.parquet", "suspension_events_resolved.parquet", "active_universe_daily.parquet",
    "unresolved_observed_trading.parquet",
    "liquidity_features.parquet", "terminal_events.parquet", "data_release_manifest.json",
    "trading_calendar.parquet",
    "company_name_history.parquet", "isin_history.parquet", "corporate_action_boundary_validation.parquet",
    "research_universe_monthly.parquet", "required_research_security.parquet",
    "research_release_manifest.json", "partitioned_artifacts_manifest.json",
]

REQUIRED_RESEARCH_REPORTS = [
    "data_source_coverage.md", "raw_integrity_audit.md", "research_universe_coverage.md", "research_identity_priority.md", "research_identity_promotion.md",
    "research_price_adjustment_promotion.md", "research_universe_corporate_action_audit.md",
    "session_correct_liquidity_audit.md", "research_universe_stability.md", "survivorship_audit.md",
    "current_survivor_comparison.md", "research_scale.md",
]

REQUIRED_PARTITIONED_ARTIFACTS = {
    "daily_prices_raw.parquet",
    "daily_prices_adjusted.parquet",
    "liquidity_features.parquet",
    "active_universe_daily.parquet",
}


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
        if (case.get("classname") or "").endswith("test_model_arena_handoff")
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


def invariant_validation_summary(path: Path) -> dict:
    report = json.loads(path.read_text(encoding="utf-8"))
    failures = {
        key: value for key, value in report.items()
        if key != "status" and isinstance(value, (int, float)) and value != 0
    }
    return {
        "status": report.get("status"),
        "failure_count": len(failures),
        "failures": failures,
    }


def source_coverage_summary(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    status = "PASS" if "Source integrity gate: `PASS`." in text else "FAIL"
    return {"status": status}


def raw_integrity_summary(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    status = "PASS" if "RAW integrity gate: `PASS`." in text else "FAIL"
    return {"status": status}


def is_ancestor(ancestor: str | None, descendant: str | None) -> bool:
    if not ancestor or not descendant:
        return False
    try:
        subprocess.run(["git", "merge-base", "--is-ancestor", ancestor, descendant], check=True, capture_output=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return ancestor == descendant


def ci_summary(path: Path, manifest: dict) -> dict:
    report = json.loads(path.read_text(encoding="utf-8"))
    jobs = report.get("jobs") or []
    return {
        "workflow_name": report.get("workflow_name"),
        "run_id": report.get("run_id"),
        "run_url": report.get("run_url"),
        "head_sha": report.get("head_sha"),
        "release_git_commit": manifest.get("git_commit"),
        "status": report.get("status"),
        "conclusion": report.get("conclusion"),
        "job_count": len(jobs),
        "failed_jobs": [job.get("name") for job in jobs if job.get("conclusion") != "success"],
        "matches_release_git_commit": report.get("head_sha") == manifest.get("git_commit"),
        "descends_from_release_git_commit": is_ancestor(manifest.get("git_commit"), report.get("head_sha")),
    }


def partition_summary(path: Path) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    artifacts = manifest.get("artifacts") or []
    partitioned_artifacts = [item.get("source_artifact") for item in artifacts]
    missing_required = sorted(REQUIRED_PARTITIONED_ARTIFACTS - set(partitioned_artifacts))
    return {
        "layout": manifest.get("layout"),
        "status": manifest.get("status"),
        "artifact_count": len(artifacts),
        "failed_artifacts": [item.get("source_artifact") for item in artifacts if item.get("status") != "PASS"],
        "missing_required_artifacts": missing_required,
        "partitioned_artifacts": partitioned_artifacts,
        "file_count": sum(int(item.get("file_count") or 0) for item in artifacts),
    }


def data_manifest_contract_failures(release: Path, manifest: dict) -> list[str]:
    failures: list[str] = []
    if manifest.get("release_id") != release.name:
        failures.append("data manifest release_id does not match release directory")
    if not manifest.get("git_commit") or manifest.get("git_commit") == "UNKNOWN":
        failures.append("data manifest git_commit is missing")
    coverage = manifest.get("coverage") or {}
    for key in ("observed_start", "observed_end", "security_count", "observation_count"):
        if coverage.get(key) is None:
            failures.append(f"data manifest coverage.{key} is missing")
    source_coverage = manifest.get("source_coverage") or {}
    for key in ("source_verified_start", "source_verified_end", "verification_basis"):
        if not source_coverage.get(key):
            failures.append(f"data manifest source_coverage.{key} is missing")
    research_coverage = manifest.get("research_coverage") or {}
    expected_research = {
        "research_verified_start": "2013-01-01",
        "universe_profile": "NSE_BROAD_LIQUID_PIT_V1",
        "profile_version": "LIQUID_V1",
        "priority_scope": "LIQUID_V1_OR_HISTORICAL_TOP750",
    }
    for key, expected in expected_research.items():
        if research_coverage.get(key) != expected:
            failures.append(f"data manifest research_coverage.{key} is not {expected}")
    if not research_coverage.get("research_verified_end"):
        failures.append("data manifest research_coverage.research_verified_end is missing")
    for key in ("source_manifest_sha256", "config_sha256", "manual_override_sha256"):
        digest = manifest.get(key)
        if not isinstance(digest, str) or len(digest) != 64:
            failures.append(f"data manifest {key} is missing or invalid")
    parser_versions = manifest.get("parser_versions") or {}
    for key in ("nse_bhavcopy", "canonicalization"):
        if not parser_versions.get(key):
            failures.append(f"data manifest parser_versions.{key} is missing")
    return failures


def research_manifest_contract_failures(release: Path, manifest: dict, research_manifest: dict) -> list[str]:
    failures: list[str] = []
    if not research_manifest:
        return ["missing research_release_manifest.json contract"]
    if research_manifest.get("release_id") != release.name:
        failures.append("research manifest release_id does not match release directory")
    if not research_manifest.get("git_sha"):
        failures.append("research manifest is missing git_sha")

    quality = research_manifest.get("research_quality") or {}
    expected_quality = {
        "status": "RESEARCH_HIGH_CONFIDENCE",
        "start": "2013-01-01",
        "universe_profile": "NSE_BROAD_LIQUID_PIT_V1",
        "profile_version": "LIQUID_V1",
        "priority_scope": "LIQUID_V1_OR_HISTORICAL_TOP750",
    }
    for key, expected in expected_quality.items():
        if quality.get(key) != expected:
            failures.append(f"research_quality.{key} is not {expected}")
    if not quality.get("end"):
        failures.append("research_quality.end is missing")
    if not quality.get("monthly_snapshot_start"):
        failures.append("research_quality.monthly_snapshot_start is missing")

    coverage = research_manifest.get("source_coverage") or {}
    for key in ("observed_start", "observed_end", "research_start", "research_end"):
        if not coverage.get(key):
            failures.append(f"source_coverage.{key} is missing")
    data_coverage = manifest.get("coverage") or {}
    for key in ("observed_start", "observed_end"):
        if data_coverage.get(key) and coverage.get(key) != data_coverage.get(key):
            failures.append(f"source_coverage.{key} does not match data manifest coverage")

    policy = research_manifest.get("known_policy") or {}
    expected_policy = {
        "signals": "price-return adjusted close",
        "execution": "raw nominal OHLC",
        "terminal_values": "explicit recovery scenarios; no invented canonical value",
    }
    for key, expected in expected_policy.items():
        if policy.get(key) != expected:
            failures.append(f"known_policy.{key} is not the published downstream contract")
    expected_contract_fields = {
        "required_quality_threshold": "RESEARCH_IDENTITY_OK_AND_PRICE_ACTION_OK_FOR_LIQUID_V1_OR_HISTORICAL_TOP750",
        "recommended_signal_price_series": "price_return_adjusted_close",
        "raw_execution_price_artifact": "daily_prices_raw.parquet",
        "liquidity_artifact": "liquidity_features.parquet",
        "terminal_value_policy_requirement": "DOWNSTREAM_RECOVERY_SENSITIVITY_REQUIRED_WHEN_CANONICAL_TERMINAL_VALUE_UNKNOWN",
    }
    for key, expected in expected_contract_fields.items():
        if research_manifest.get(key) != expected:
            failures.append(f"research manifest {key} is not {expected}")

    required_artifacts = {
        "research_universe_monthly.parquet",
        "required_research_security.parquet",
        "liquidity_features.parquet",
        "daily_prices_raw.parquet",
        "daily_prices_adjusted.parquet",
        "corporate_actions.parquet",
        "corporate_action_boundary_validation.parquet",
        "trading_status_intervals.parquet",
        "suspension_events_resolved.parquet",
        "unresolved_observed_trading.parquet",
    }
    artifacts = research_manifest.get("artifacts") or {}
    for name in required_artifacts:
        if name not in artifacts:
            failures.append(f"research manifest artifact hash missing for {name}")
    monthly_contract = {
        "date",
        "security_id",
        "listing_episode_id",
        "symbol_at_date",
        "instrument_type",
        "identity_quality",
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
        "profile_id",
        "profile_version",
        "as_of_date",
        "eligibility_result",
        "eligibility_reason_codes",
    }
    published_monthly_contract = set(research_manifest.get("research_universe_monthly_contract") or [])
    missing_monthly_contract = sorted(monthly_contract - published_monthly_contract)
    if missing_monthly_contract:
        failures.append(f"research manifest research_universe_monthly_contract misses {missing_monthly_contract}")
    required_security_contract = {
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
    }
    published_required_security_contract = set(research_manifest.get("required_research_security_contract") or [])
    missing_required_security_contract = sorted(required_security_contract - published_required_security_contract)
    if missing_required_security_contract:
        failures.append(f"research manifest required_research_security_contract misses {missing_required_security_contract}")

    for key in ("config_sha256", "manual_override_sha256", "research_invariant_validation_sha256", "test_result_sha256", "ci_status_sha256"):
        if not research_manifest.get(key):
            failures.append(f"research manifest {key} is missing")
    quality_reports = research_manifest.get("quality_reports") or {}
    if not quality_reports:
        failures.append("research manifest quality_reports are missing")
    for name in REQUIRED_RESEARCH_REPORTS:
        if name not in quality_reports:
            failures.append(f"research manifest quality report hash missing for {name}")
    limitations = research_manifest.get("known_limitations") or []
    required_limit_tokens = (
        "exploratory",
        "terminal",
        "dividend",
        "market-cap",
        "sector",
        "retrieval",
    )
    joined_limitations = " ".join(str(item).lower() for item in limitations)
    if len(limitations) < 5:
        failures.append("research manifest known_limitations are incomplete")
    for token in required_limit_tokens:
        if token not in joined_limitations:
            failures.append(f"research manifest known_limitations do not mention {token}")
    if manifest.get("git_commit") and research_manifest.get("git_sha") != manifest.get("git_commit"):
        failures.append("research manifest git_sha does not match data manifest git_commit")
    return failures


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
    ci_status_report = report_dir / f"ci_status_{release.name}.json"
    if research_manifest.get("ci_status_sha256") and not ci_status_report.exists():
        missing_reports.append(ci_status_report.name)
    partition_manifest_path = release / "partitioned_artifacts_manifest.json"
    manifest_mismatch = manifest.get("release_id") != release.name
    research_quality_ok = research_manifest.get("research_quality", {}).get("status") == "RESEARCH_HIGH_CONFIDENCE"
    data_contract_failures = data_manifest_contract_failures(release, manifest)
    research_contract_failures = research_manifest_contract_failures(release, manifest, research_manifest)
    if missing or missing_reports or manifest_mismatch or not research_quality_ok or data_contract_failures or research_contract_failures:
        rows = [f"# Release completion audit: `{manifest.get('release_id')}`", "", "## Required artifact checks", ""]
        rows.extend(f"- {'PASS' if name not in missing else 'FAIL'}: `{name}`" for name in REQUIRED)
        if manifest_mismatch:
            rows.extend(["", f"- FAIL: manifest release_id does not match directory `{release.name}`"])
        if not research_quality_ok:
            rows.extend(["", "- FAIL: research quality is not RESEARCH_HIGH_CONFIDENCE"])
        rows.extend(f"- FAIL: {failure}" for failure in data_contract_failures)
        rows.extend(f"- FAIL: {failure}" for failure in research_contract_failures)
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
    ci_expected = research_manifest.get("ci_status_sha256")
    if ci_expected and (not ci_status_report.is_file() or sha256(ci_status_report) != ci_expected):
        hash_mismatches.append(f"report/{ci_status_report.name}")
    partition_expected = research_manifest.get("partitioned_artifacts_manifest_sha256")
    if partition_expected and (not partition_manifest_path.is_file() or sha256(partition_manifest_path) != partition_expected):
        hash_mismatches.append(f"release/{partition_manifest_path.name}")
    if hash_mismatches:
        rows = [f"# Release completion audit: `{manifest.get('release_id')}`", "", "## Artifact hash checks", ""]
        rows.extend(f"- FAIL: `{key}`" if key in hash_mismatches else f"- PASS: `{key}`" for key in sorted(manifest.get("artifacts", {})))
        Path(args.out).write_text("\n".join(rows) + "\n", encoding="utf-8")
        print(f"WROTE {args.out}")
        print("RELEASE_AUDIT_FAILED")
        for key in hash_mismatches:
            print(f"- artifact hash mismatch: {key}")
        raise SystemExit(1)
    invariant_summary = invariant_validation_summary(validation_path)
    source_summary = source_coverage_summary(report_dir / "data_source_coverage.md")
    raw_summary = raw_integrity_summary(report_dir / "raw_integrity_audit.md")
    test_summary = junit_summary(test_result_report)
    ci = ci_summary(ci_status_report, manifest) if ci_status_report.exists() else {
        "workflow_name": None,
        "run_id": None,
        "run_url": None,
        "head_sha": None,
        "release_git_commit": manifest.get("git_commit"),
        "status": "NOT_RECORDED",
        "conclusion": None,
        "job_count": 0,
        "failed_jobs": [],
        "matches_release_git_commit": False,
        "descends_from_release_git_commit": False,
    }
    partitions = partition_summary(partition_manifest_path)
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
    missing_adjusted_contract = []
    adjusted = release / "daily_prices_adjusted.parquet"
    if adjusted.exists():
        quality = dict(con.execute("SELECT total_return_quality, count(*) FROM read_parquet(?) GROUP BY 1", [str(adjusted)]).fetchall())
        adjusted_columns = {row[0] for row in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(adjusted)]).fetchall()}
        missing_adjusted_contract = sorted({"price_return_adjusted_close", "total_return_adjusted_close"} - adjusted_columns)
    liquidity_window_failures = con.execute("""
        SELECT COUNT(*) FROM read_parquet(?)
        WHERE liquidity_window_definition IS DISTINCT FROM 'OFFICIAL_NSE_SESSION_WINDOW'
    """, [str(release / "liquidity_features.parquet")]).fetchone()[0]
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
        f"- Adjusted-price contract missing columns: `{missing_adjusted_contract}`.",
        f"- Liquidity feature rows with non-official session window: {liquidity_window_failures:,}.",
        f"- Corporate-action boundary validation: `{json.dumps(boundary_quality, sort_keys=True)}`." if boundary_path.exists() else "- Corporate-action boundary validation: not published.",
        f"- RAW integrity validation: `{json.dumps(raw_summary, sort_keys=True)}`.",
        f"- Source coverage validation: `{json.dumps(source_summary, sort_keys=True)}`.",
        f"- Research invariant validation: `{json.dumps(invariant_summary, sort_keys=True)}`.",
        f"- Test results: `{json.dumps(test_summary, sort_keys=True)}`.",
        f"- GitHub Actions CI: `{json.dumps(ci, sort_keys=True)}`.",
        f"- Partitioned sidecar layout: `{json.dumps(partitions, sort_keys=True)}`.",
        "",
        "## Required artifact checks",
        "",
    ]
    failures = []
    if manifest.get("release_id") != release.name:
        failures.append(f"manifest release_id {manifest.get('release_id')!r} does not match directory {release.name!r}")
    if not research_quality_ok:
        failures.append("research release is not RESEARCH_HIGH_CONFIDENCE")
    failures.extend(data_contract_failures)
    failures.extend(research_contract_failures)
    failures.extend(f"missing required research report: {name}" for name in missing_reports)
    if invariant_summary["status"] != "PASS" or invariant_summary["failure_count"]:
        failures.append(f"research invariant validation is not clean: {json.dumps(invariant_summary, sort_keys=True)}")
    if source_summary["status"] != "PASS":
        failures.append(f"source coverage validation is not clean: {json.dumps(source_summary, sort_keys=True)}")
    if raw_summary["status"] != "PASS":
        failures.append(f"RAW integrity validation is not clean: {json.dumps(raw_summary, sort_keys=True)}")
    if missing_adjusted_contract:
        failures.append(f"adjusted-price artifact is missing contract columns: {missing_adjusted_contract}")
    if liquidity_window_failures:
        failures.append(f"liquidity features are not all official-session windows: {liquidity_window_failures}")
    if test_summary["tests"] <= 0 or test_summary["failures"] or test_summary["errors"]:
        failures.append(f"test result report is not clean: {json.dumps(test_summary, sort_keys=True)}")
    if not test_summary["model_arena_handoff_passed"]:
        failures.append("Model Arena handoff smoke test did not pass in release evidence")
    if research_manifest.get("ci_status_sha256") and (ci["status"] != "completed" or ci["conclusion"] != "success" or not ci["descends_from_release_git_commit"] or ci["failed_jobs"]):
        failures.append(f"GitHub Actions CI evidence is not clean: {json.dumps(ci, sort_keys=True)}")
    if partitions["status"] != "PASS" or partitions["artifact_count"] < 4 or partitions["failed_artifacts"] or partitions["missing_required_artifacts"]:
        failures.append(f"partitioned sidecar evidence is not clean: {json.dumps(partitions, sort_keys=True)}")
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
