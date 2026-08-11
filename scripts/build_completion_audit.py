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

from india_active_universe.profiles import (
    ACTIVE_DEFINITION,
    ADJUSTED_PRICE_ARTIFACT,
    CANDIDATE_AUDIT_STATUS_VALUES,
    CANDIDATE_ADVISORY_READINESS_KEYS,
    CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS,
    CANDIDATE_DECISION_GATE_KEYS,
    CANDIDATE_DECISION_REQUIRED_FIELDS,
    CANDIDATE_DECISION_GATE_VALUES,
    CANDIDATE_GATE_PASS_INTERPRETATION,
    CANDIDATE_HARD_FAILURE_KEYS,
    CANDIDATE_NUMERIC_HARD_FAILURE_KEYS,
    CANDIDATE_FAIL_VALUE,
    CANDIDATE_NOT_RECORDED_VALUE,
    CANDIDATE_PASS_VALUE,
    CANDIDATE_PROMOTION_INTERPRETATION_VALUES,
    CANDIDATE_RESEARCH_START_DATES,
    COMPONENT_QUALITY,
    CORPORATE_ACTIONS_ARTIFACT,
    CORPORATE_ACTION_BOUNDARY_ARTIFACT,
    DATASET_QUALITY_TIER,
    DATA_RELEASE_MANIFEST_ARTIFACT,
    EXECUTION_POLICY,
    FEATURE_READINESS_WINDOWS,
    LIQUIDITY_ARTIFACT,
    LIQUID_V1_DEFINITION,
    PARTITIONED_RELEASE_ARTIFACTS,
    PRIORITY_SCOPE,
    PROFILE_ID,
    PROFILE_VERSION,
    PARSER_VERSIONS,
    PARTITIONED_ARTIFACTS_MANIFEST,
    RAW_EXECUTION_PRICE_ARTIFACT,
    RECOMMENDED_SIGNAL_PRICE_SERIES,
    RESEARCH_RELEASE_MANIFEST_ARTIFACT,
    RESEARCH_MANIFEST_ARTIFACTS,
    RESEARCH_HIGH_CONFIDENCE_STATUS,
    RESEARCH_MONTHLY_SNAPSHOT_START,
    RESEARCH_START_DATE,
    RESEARCH_UNIVERSE_MONTHLY_ARTIFACT,
    REQUIRED_RELEASE_ARTIFACTS,
    REQUIRED_RESEARCH_REPORTS,
    REQUIRED_QUALITY_THRESHOLD,
    SECURITY_MASTER_ARTIFACT,
    SIGNAL_POLICY,
    SOURCE_BUILD_MODE,
    SOURCE_OBSERVED_START_DATE,
    SOURCE_MANIFEST_ARTIFACT,
    TERMINAL_VALUE_POLICY,
    TERMINAL_VALUE_POLICY_REQUIREMENT,
    TERMINAL_EVENTS_ARTIFACT,
    TOP_LIQUIDITY_RANKING_METRIC,
    TRADING_STATUS_INTERVALS_ARTIFACT,
)


REQUIRED = list(REQUIRED_RELEASE_ARTIFACTS)

REQUIRED_PARTITIONED_ARTIFACTS = set(PARTITIONED_RELEASE_ARTIFACTS)

EXPECTED_INVARIANT_VALIDATION_METRICS = {
    "monthly_snapshot_start_mismatch",
    "pre_research_start_rows",
    "non_month_final_session_dates",
    "duplicate_month_security_rows",
    "non_ordinary_rows",
    "non_active_trading_rows",
    "missing_quality_fields",
    "required_scope_quality_failures",
    "required_scope_missing_research_fields",
    "top_liquidity_null_metric_failures",
    "required_scope_missing_from_required_artifact",
    "required_artifact_security_without_monthly_scope",
    "required_artifact_flag_failures",
    "required_artifact_date_range_failures",
    "required_artifact_rank_evidence_failures",
    "required_artifact_liquidity_evidence_failures",
    "required_artifact_identity_quality_failures",
    "required_artifact_price_adjustment_failures",
    "required_artifact_status_failures",
    "required_artifact_instrument_classification_failures",
    "future_listing_rows",
    "non_calendar_dates",
    "liquid_predicate_failures",
    "artifact_alias_failures",
    "eligible_profile_metadata_failures",
    "excluded_profile_metadata_failures",
    "top_liquidity_flag_failures",
}

EXPECTED_CANDIDATE_HARD_FAILURE_KEYS = set(CANDIDATE_HARD_FAILURE_KEYS)
EXPECTED_CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS = set(CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS)
EXPECTED_CANDIDATE_NUMERIC_HARD_FAILURE_KEYS = set(CANDIDATE_NUMERIC_HARD_FAILURE_KEYS)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_sha256_digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value.lower())


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
    multi_era_cases = [
        case for case in root.iter("testcase")
        if (case.get("classname") or "").endswith("test_multi_era_source_fixture")
        and case.get("name") == "test_real_nse_source_eras_build_to_liquidity_and_adjusted_prices"
    ]
    multi_era_passed = bool(multi_era_cases) and all(case.find("skipped") is None for case in multi_era_cases)
    return {
        "tests": tests,
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
        "model_arena_handoff_passed": handoff_passed,
        "multi_era_source_fixture_passed": multi_era_passed,
    }


def invariant_validation_summary(path: Path) -> dict:
    report = json.loads(path.read_text(encoding="utf-8"))
    failures = {
        key: value for key, value in report.items()
        if key != "status" and isinstance(value, (int, float)) and value != 0
    }
    missing_metrics = sorted(EXPECTED_INVARIANT_VALIDATION_METRICS - set(report))
    return {
        "status": report.get("status"),
        "failure_count": len(failures) + len(missing_metrics),
        "failures": failures,
        "missing_metrics": missing_metrics,
    }


def candidate_hard_failure_type_failures(hard_failures: dict) -> list[str]:
    failures = []
    for key in sorted(EXPECTED_CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS):
        if type(hard_failures.get(key)) is not bool:
            failures.append(key)
    for key in sorted(EXPECTED_CANDIDATE_NUMERIC_HARD_FAILURE_KEYS):
        if type(hard_failures.get(key)) is not int:
            failures.append(key)
    return failures


def candidate_promotion_audit_summary(candidate_promotion_report: dict) -> dict:
    malformed_candidate_report = []
    if candidate_promotion_report.get("profile") != PROFILE_ID:
        malformed_candidate_report.append("profile")
    if candidate_promotion_report.get("profile_version") != PROFILE_VERSION:
        malformed_candidate_report.append("profile_version")
    if candidate_promotion_report.get("priority_scope") != PRIORITY_SCOPE:
        malformed_candidate_report.append("priority_scope")
    if candidate_promotion_report.get("control_start") != RESEARCH_START_DATE:
        malformed_candidate_report.append("control_start")
    if candidate_promotion_report.get("candidate_start_dates") != list(CANDIDATE_RESEARCH_START_DATES):
        malformed_candidate_report.append("candidate_start_dates")
    if candidate_promotion_report.get("required_prior_sessions_for_full_readiness") != max(FEATURE_READINESS_WINDOWS.values()):
        malformed_candidate_report.append("required_prior_sessions_for_full_readiness")
    candidate_audits = candidate_promotion_report.get("candidate_audits") or []
    candidate_start_values = [item.get("candidate_start") for item in candidate_audits if isinstance(item, dict)]
    candidate_starts = set(candidate_start_values)
    missing_candidate_starts = sorted(set(CANDIDATE_RESEARCH_START_DATES) - candidate_starts)
    unexpected_candidate_starts = sorted(candidate_starts - set(CANDIDATE_RESEARCH_START_DATES))
    duplicate_candidate_starts = sorted(
        candidate_start
        for candidate_start in candidate_starts
        if candidate_start_values.count(candidate_start) > 1
    )
    malformed_candidate_audits = []
    for item in candidate_audits:
        if not isinstance(item, dict):
            malformed_candidate_audits.append(None)
            continue
        hard_failures = item.get("hard_failures")
        feature_readiness = item.get("feature_readiness")
        refined_earliest_passing_snapshot = item.get("refined_earliest_passing_snapshot")
        hard_failure_keys = set(hard_failures or {}) if isinstance(hard_failures, dict) else set()
        required_rows = item.get("required_rows")
        fully_warmed_required_rows = item.get("fully_warmed_required_rows")
        monthly_snapshots_after_decision = item.get("monthly_snapshots_after_decision")
        active_hard_failures = (
            [
                value for value in hard_failures.values()
                if value is True or (isinstance(value, int) and value != 0)
            ]
            if isinstance(hard_failures, dict)
            else []
        )
        if (
            item.get("profile") != PROFILE_ID
            or item.get("profile_version") != PROFILE_VERSION
            or item.get("priority_scope") != PRIORITY_SCOPE
            or item.get("control_start") != RESEARCH_START_DATE
            or item.get("required_prior_sessions_for_full_readiness") != max(FEATURE_READINESS_WINDOWS.values())
            or item.get("status") not in {"PASS", "FAIL"}
            or not isinstance(hard_failures, dict)
            or not isinstance(feature_readiness, dict)
            or type(feature_readiness.get("feature_warmup_not_ready")) is not bool
            or "refined_earliest_passing_snapshot" not in item
            or (refined_earliest_passing_snapshot is not None and not isinstance(refined_earliest_passing_snapshot, str))
            or hard_failure_keys != EXPECTED_CANDIDATE_HARD_FAILURE_KEYS
            or bool(candidate_hard_failure_type_failures(hard_failures))
            or not isinstance(required_rows, int)
            or not isinstance(fully_warmed_required_rows, int)
            or not isinstance(monthly_snapshots_after_decision, int)
            or fully_warmed_required_rows > required_rows
            or (item.get("status") == CANDIDATE_PASS_VALUE and bool(active_hard_failures))
            or (item.get("status") == CANDIDATE_PASS_VALUE and refined_earliest_passing_snapshot is None)
            or (item.get("status") == CANDIDATE_FAIL_VALUE and not active_hard_failures)
            or (item.get("status") == CANDIDATE_PASS_VALUE and monthly_snapshots_after_decision <= 0)
            or (monthly_snapshots_after_decision <= 0 and hard_failures.get("decision_window_snapshots_missing") is False)
            or (monthly_snapshots_after_decision > 0 and hard_failures.get("decision_window_snapshots_missing") is True)
        ):
            malformed_candidate_audits.append(item.get("candidate_start"))
    return {
        "candidate_count": len(candidate_audits),
        "missing_candidate_starts": missing_candidate_starts,
        "unexpected_candidate_starts": unexpected_candidate_starts,
        "duplicate_candidate_starts": duplicate_candidate_starts,
        "malformed_candidate_audits": malformed_candidate_audits,
        "malformed_candidate_report": malformed_candidate_report,
    }


def candidate_manifest_audit_consistency_failures(research_manifest: dict, candidate_promotion_report: dict) -> list[str]:
    failures: list[str] = []
    candidate_audits = candidate_promotion_report.get("candidate_audits") or []
    audit_by_start = {
        item.get("candidate_start"): item
        for item in candidate_audits
        if isinstance(item, dict)
    }
    for decision in research_manifest.get("candidate_promotion_decisions") or []:
        if not isinstance(decision, dict):
            continue
        candidate_start = decision.get("candidate_start")
        audit = audit_by_start.get(candidate_start)
        if not audit:
            continue
        if decision.get("candidate_audit_status") != audit.get("status"):
            failures.append(f"candidate {candidate_start} decision status does not match candidate audit report")
        if decision.get("hard_failures") != audit.get("hard_failures"):
            failures.append(f"candidate {candidate_start} decision hard_failures do not match candidate audit report")
        if decision.get("feature_readiness") != audit.get("feature_readiness"):
            failures.append(f"candidate {candidate_start} decision feature_readiness does not match candidate audit report")
        if decision.get("refined_earliest_passing_snapshot") != audit.get("refined_earliest_passing_snapshot"):
            failures.append(f"candidate {candidate_start} decision refined_earliest_passing_snapshot does not match candidate audit report")
    return failures


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
    if manifest.get("build_mode") != SOURCE_BUILD_MODE:
        failures.append(f"data manifest build_mode is not {SOURCE_BUILD_MODE}")
    coverage = manifest.get("coverage") or {}
    for key in ("observed_start", "observed_end", "security_count", "observation_count"):
        if coverage.get(key) is None:
            failures.append(f"data manifest coverage.{key} is missing")
    if coverage.get("observed_start") != SOURCE_OBSERVED_START_DATE:
        failures.append(f"data manifest coverage.observed_start is not {SOURCE_OBSERVED_START_DATE}")
    source_coverage = manifest.get("source_coverage") or {}
    for key in ("source_verified_start", "source_verified_end", "verification_basis"):
        if not source_coverage.get(key):
            failures.append(f"data manifest source_coverage.{key} is missing")
    if source_coverage.get("source_verified_start") != SOURCE_OBSERVED_START_DATE:
        failures.append(f"data manifest source_coverage.source_verified_start is not {SOURCE_OBSERVED_START_DATE}")
    if source_coverage.get("source_verified_start") != coverage.get("observed_start"):
        failures.append("data manifest source_coverage.source_verified_start does not match coverage.observed_start")
    if source_coverage.get("source_verified_end") != coverage.get("observed_end"):
        failures.append("data manifest source_coverage.source_verified_end does not match coverage.observed_end")
    research_coverage = manifest.get("research_coverage") or {}
    allowed_research_starts = set(CANDIDATE_RESEARCH_START_DATES) | {RESEARCH_START_DATE}
    if research_coverage.get("research_verified_start") not in allowed_research_starts:
        failures.append(f"data manifest research_coverage.research_verified_start is not one of {sorted(allowed_research_starts)}")
    expected_research = {
        "universe_profile": PROFILE_ID,
        "profile_version": PROFILE_VERSION,
        "priority_scope": PRIORITY_SCOPE,
    }
    for key, expected in expected_research.items():
        if research_coverage.get(key) != expected:
            failures.append(f"data manifest research_coverage.{key} is not {expected}")
    if not research_coverage.get("monthly_snapshot_start"):
        failures.append("data manifest research_coverage.monthly_snapshot_start is missing")
    if not research_coverage.get("research_verified_end"):
        failures.append("data manifest research_coverage.research_verified_end is missing")
    warmup = manifest.get("warmup_coverage") or {}
    if warmup.get("feature_readiness_windows") != FEATURE_READINESS_WINDOWS:
        failures.append("data manifest warmup_coverage.feature_readiness_windows is not the published readiness contract")
    if not isinstance(warmup.get("feature_ready_dates"), dict):
        failures.append("data manifest warmup_coverage.feature_ready_dates is missing or not an object")
    if warmup.get("required_prior_sessions_for_full_readiness") != max(FEATURE_READINESS_WINDOWS.values()):
        failures.append("data manifest warmup_coverage.required_prior_sessions_for_full_readiness is not the maximum readiness window")
    if "earliest_fully_warmed_date" not in warmup:
        failures.append("data manifest warmup_coverage.earliest_fully_warmed_date is missing")
    intervals = manifest.get("research_quality_intervals")
    if not isinstance(intervals, list) or not intervals:
        failures.append("data manifest research_quality_intervals is missing or empty")
    elif not any(
        item.get("status") == RESEARCH_HIGH_CONFIDENCE_STATUS
        and item.get("profile") == PROFILE_ID
        and item.get("profile_version") == PROFILE_VERSION
        and item.get("priority_scope") == PRIORITY_SCOPE
        for item in intervals
        if isinstance(item, dict)
    ):
        failures.append("data manifest research_quality_intervals has no scoped RESEARCH_HIGH_CONFIDENCE interval")
    component_quality = manifest.get("component_quality") or {}
    for key, expected in COMPONENT_QUALITY.items():
        if component_quality.get(key) != expected:
            failures.append(f"data manifest component_quality.{key} is not {expected}")
    if manifest.get("definition") != ACTIVE_DEFINITION:
        failures.append(f"data manifest definition is not {ACTIVE_DEFINITION}")
    if manifest.get("quality_tier") != DATASET_QUALITY_TIER:
        failures.append(f"data manifest quality_tier is not {DATASET_QUALITY_TIER}")
    for key in ("source_manifest_sha256", "config_sha256", "manual_override_sha256"):
        digest = manifest.get(key)
        if not is_sha256_digest(digest):
            failures.append(f"data manifest {key} is missing or invalid")
    parser_versions = manifest.get("parser_versions") or {}
    for key, expected in PARSER_VERSIONS.items():
        if parser_versions.get(key) != expected:
            failures.append(f"data manifest parser_versions.{key} is not {expected}")
    artifacts = manifest.get("artifacts") or {}
    source_manifest_key = f"release/{SOURCE_MANIFEST_ARTIFACT}"
    if artifacts.get(source_manifest_key) != manifest.get("source_manifest_sha256"):
        failures.append(f"data manifest {source_manifest_key} hash does not match source_manifest_sha256")
    for name in REQUIRED:
        if name in {DATA_RELEASE_MANIFEST_ARTIFACT, RESEARCH_RELEASE_MANIFEST_ARTIFACT}:
            continue
        if f"release/{name}" not in artifacts:
            failures.append(f"data manifest artifact hash missing for release/{name}")
    return failures


def research_manifest_contract_failures(release: Path, manifest: dict, research_manifest: dict) -> list[str]:
    failures: list[str] = []
    if not research_manifest:
        return [f"missing {RESEARCH_RELEASE_MANIFEST_ARTIFACT} contract"]
    if research_manifest.get("release_id") != release.name:
        failures.append("research manifest release_id does not match release directory")
    if not research_manifest.get("git_sha"):
        failures.append("research manifest is missing git_sha")

    quality = research_manifest.get("research_quality") or {}
    expected_quality = {
        "status": RESEARCH_HIGH_CONFIDENCE_STATUS,
        "universe_profile": PROFILE_ID,
        "profile_version": PROFILE_VERSION,
        "priority_scope": PRIORITY_SCOPE,
    }
    for key, expected in expected_quality.items():
        if quality.get(key) != expected:
            failures.append(f"research_quality.{key} is not {expected}")
    data_research_coverage = manifest.get("research_coverage") or {}
    if quality.get("start") != data_research_coverage.get("research_verified_start"):
        failures.append("research_quality.start does not match data manifest research_coverage.research_verified_start")
    if not quality.get("end"):
        failures.append("research_quality.end is missing")
    expected_monthly_start = data_research_coverage.get("monthly_snapshot_start") or RESEARCH_MONTHLY_SNAPSHOT_START
    if quality.get("monthly_snapshot_start") != expected_monthly_start:
        failures.append(f"research_quality.monthly_snapshot_start is not {expected_monthly_start}")

    coverage = research_manifest.get("source_coverage") or {}
    for key in ("observed_start", "observed_end", "research_start", "research_end"):
        if not coverage.get(key):
            failures.append(f"source_coverage.{key} is missing")
    if coverage.get("observed_start") != SOURCE_OBSERVED_START_DATE:
        failures.append(f"source_coverage.observed_start is not {SOURCE_OBSERVED_START_DATE}")
    if coverage.get("research_start") != quality.get("start"):
        failures.append("source_coverage.research_start does not match research_quality.start")
    if coverage.get("research_end") != quality.get("end"):
        failures.append("source_coverage.research_end does not match research_quality.end")
    data_coverage = manifest.get("coverage") or {}
    for key in ("observed_start", "observed_end"):
        if data_coverage.get(key) and coverage.get(key) != data_coverage.get(key):
            failures.append(f"source_coverage.{key} does not match data manifest coverage")

    warmup = research_manifest.get("warmup_coverage") or {}
    if warmup.get("feature_readiness_windows") != FEATURE_READINESS_WINDOWS:
        failures.append("research manifest warmup_coverage.feature_readiness_windows is not the published readiness contract")
    if not isinstance(warmup.get("feature_ready_dates"), dict):
        failures.append("research manifest warmup_coverage.feature_ready_dates is missing or not an object")
    if warmup.get("required_prior_sessions_for_full_readiness") != max(FEATURE_READINESS_WINDOWS.values()):
        failures.append("research manifest warmup_coverage.required_prior_sessions_for_full_readiness is not the maximum readiness window")
    if "earliest_fully_warmed_date" not in warmup:
        failures.append("research manifest warmup_coverage.earliest_fully_warmed_date is missing")

    intervals = research_manifest.get("research_quality_intervals")
    if not isinstance(intervals, list) or not intervals:
        failures.append("research manifest research_quality_intervals is missing or empty")
    elif not any(
        item.get("status") == RESEARCH_HIGH_CONFIDENCE_STATUS
        and item.get("profile") == PROFILE_ID
        and item.get("profile_version") == PROFILE_VERSION
        and item.get("priority_scope") == PRIORITY_SCOPE
        for item in intervals
        if isinstance(item, dict)
    ):
        failures.append("research manifest research_quality_intervals has no scoped RESEARCH_HIGH_CONFIDENCE interval")
    candidate_decisions = research_manifest.get("candidate_promotion_decisions")
    if not isinstance(candidate_decisions, list):
        failures.append("research manifest candidate_promotion_decisions is missing or not a list")
    else:
        earliest_candidate_gate_pass_start = research_manifest.get("earliest_candidate_gate_pass_start")
        if "earliest_candidate_gate_pass_start" not in research_manifest:
            failures.append("research manifest earliest_candidate_gate_pass_start is missing")
        refined_earliest_candidate_gate_pass_boundary = research_manifest.get("refined_earliest_candidate_gate_pass_boundary")
        candidate_decision_start_values = [
            item.get("candidate_start") for item in candidate_decisions
            if isinstance(item, dict)
        ]
        candidate_decision_starts = set(candidate_decision_start_values)
        duplicate_candidate_decisions = sorted(
            candidate_start
            for candidate_start in candidate_decision_starts
            if candidate_decision_start_values.count(candidate_start) > 1
        )
        required_decision_fields = set(CANDIDATE_DECISION_REQUIRED_FIELDS)
        pass_interpretation = CANDIDATE_GATE_PASS_INTERPRETATION
        missing_candidate_decisions = sorted(set(CANDIDATE_RESEARCH_START_DATES) - candidate_decision_starts)
        unexpected_candidate_decisions = sorted(candidate_decision_starts - set(CANDIDATE_RESEARCH_START_DATES))
        if missing_candidate_decisions:
            failures.append(f"research manifest candidate_promotion_decisions misses {missing_candidate_decisions}")
        if unexpected_candidate_decisions:
            failures.append(f"research manifest candidate_promotion_decisions has unexpected starts {unexpected_candidate_decisions}")
        if duplicate_candidate_decisions:
            failures.append(f"research manifest candidate_promotion_decisions has duplicate starts {duplicate_candidate_decisions}")
        if earliest_candidate_gate_pass_start is not None and earliest_candidate_gate_pass_start not in set(CANDIDATE_RESEARCH_START_DATES):
            failures.append("research manifest earliest_candidate_gate_pass_start is not a configured candidate start")
        for item in candidate_decisions:
            if not isinstance(item, dict):
                failures.append("research manifest candidate_promotion_decisions contains a non-object item")
                continue
            missing_fields = sorted(required_decision_fields - set(item))
            if missing_fields:
                failures.append(f"research manifest candidate {item.get('candidate_start')} decision misses {missing_fields}")
            if item.get("candidate_audit_status") not in CANDIDATE_AUDIT_STATUS_VALUES:
                failures.append(f"research manifest candidate {item.get('candidate_start')} has invalid candidate_audit_status")
            for gate_key in CANDIDATE_DECISION_GATE_KEYS:
                if item.get(gate_key) not in CANDIDATE_DECISION_GATE_VALUES:
                    failures.append(f"research manifest candidate {item.get('candidate_start')} has invalid {gate_key}")
            for readiness_key in CANDIDATE_ADVISORY_READINESS_KEYS:
                if item.get(readiness_key) not in CANDIDATE_DECISION_GATE_VALUES:
                    failures.append(f"research manifest candidate {item.get('candidate_start')} has invalid advisory {readiness_key}")
            feature_readiness = item.get("feature_readiness")
            if not isinstance(feature_readiness, dict):
                failures.append(f"research manifest candidate {item.get('candidate_start')} feature_readiness is not an object")
            elif type(feature_readiness.get("feature_warmup_not_ready")) is not bool:
                failures.append(f"research manifest candidate {item.get('candidate_start')} feature_readiness.feature_warmup_not_ready is not bool")
            hard_failures = item.get("hard_failures")
            if not isinstance(hard_failures, dict):
                failures.append(f"research manifest candidate {item.get('candidate_start')} hard_failures is not an object")
            elif set(hard_failures) != EXPECTED_CANDIDATE_HARD_FAILURE_KEYS:
                failures.append(f"research manifest candidate {item.get('candidate_start')} hard_failures keys do not match the candidate audit contract")
            elif candidate_hard_failure_type_failures(hard_failures):
                failures.append(f"research manifest candidate {item.get('candidate_start')} hard_failures value types do not match the candidate audit contract")
            elif item.get("candidate_audit_status") == CANDIDATE_PASS_VALUE and any(
                value is True or (isinstance(value, int) and value != 0)
                for value in hard_failures.values()
            ):
                failures.append(f"research manifest candidate {item.get('candidate_start')} claims PASS candidate audit with active hard_failures")
            elif item.get("candidate_audit_status") == CANDIDATE_FAIL_VALUE and not any(
                value is True or (isinstance(value, int) and value != 0)
                for value in hard_failures.values()
            ):
                failures.append(f"research manifest candidate {item.get('candidate_start')} claims FAIL candidate audit without active hard_failures")
            elif (
                (item.get("decision_window_gate") == CANDIDATE_PASS_VALUE and hard_failures.get("decision_window_snapshots_missing") is not False)
                or (item.get("decision_window_gate") == CANDIDATE_FAIL_VALUE and hard_failures.get("decision_window_snapshots_missing") is not True)
            ):
                failures.append(f"research manifest candidate {item.get('candidate_start')} decision_window_gate contradicts hard_failures")
            elif isinstance(feature_readiness, dict) and (
                (item.get("warmup_gate") == CANDIDATE_PASS_VALUE and feature_readiness.get("feature_warmup_not_ready") is not False)
                or (item.get("warmup_gate") == CANDIDATE_FAIL_VALUE and feature_readiness.get("feature_warmup_not_ready") is False)
            ):
                failures.append(f"research manifest candidate {item.get('candidate_start')} warmup_gate contradicts feature_readiness")
            elif (
                (item.get("session_liquidity_gate") == CANDIDATE_PASS_VALUE and int(hard_failures.get("session_liquidity_window_failures") or 0) != 0)
                or (item.get("session_liquidity_gate") == CANDIDATE_FAIL_VALUE and int(hard_failures.get("session_liquidity_window_failures") or 0) == 0)
            ):
                failures.append(f"research manifest candidate {item.get('candidate_start')} session_liquidity_gate contradicts hard_failures")
            elif item.get("identity_gate") == CANDIDATE_PASS_VALUE and int(hard_failures.get("identity_failures") or 0) != 0:
                failures.append(f"research manifest candidate {item.get('candidate_start')} identity_gate contradicts hard_failures")
            elif item.get("price_action_gate") == CANDIDATE_PASS_VALUE and (
                int(hard_failures.get("price_adjustment_failures") or 0) != 0
                or int(hard_failures.get("material_missing_factors") or 0) != 0
                or int(hard_failures.get("signal_window_non_pass_boundaries") or 0) != 0
            ):
                failures.append(f"research manifest candidate {item.get('candidate_start')} price_action_gate contradicts hard_failures")
            elif item.get("instrument_gate") == CANDIDATE_PASS_VALUE and int(hard_failures.get("instrument_failures") or 0) != 0:
                failures.append(f"research manifest candidate {item.get('candidate_start')} instrument_gate contradicts hard_failures")
            elif (
                (item.get("status_gate") == CANDIDATE_PASS_VALUE and int(hard_failures.get("status_failures") or 0) != 0)
                or (item.get("status_gate") == CANDIDATE_FAIL_VALUE and int(hard_failures.get("status_failures") or 0) == 0)
            ):
                failures.append(f"research manifest candidate {item.get('candidate_start')} status_gate contradicts hard_failures")
            if item.get("promotion_interpretation") not in CANDIDATE_PROMOTION_INTERPRETATION_VALUES:
                failures.append(f"research manifest candidate {item.get('candidate_start')} has invalid promotion_interpretation")
            if item.get("promotion_interpretation") == pass_interpretation:
                non_pass_gates = [
                    gate_key for gate_key in CANDIDATE_DECISION_GATE_KEYS
                    if item.get(gate_key) != CANDIDATE_PASS_VALUE
                ]
                if item.get("candidate_audit_status") != CANDIDATE_PASS_VALUE:
                    failures.append(f"research manifest candidate {item.get('candidate_start')} claims gate pass without PASS candidate audit")
                if non_pass_gates:
                    failures.append(f"research manifest candidate {item.get('candidate_start')} claims gate pass with non-PASS gates {non_pass_gates}")
        gate_pass_candidate_starts = sorted(
            item.get("candidate_start") for item in candidate_decisions
            if isinstance(item, dict)
            and item.get("promotion_interpretation") == pass_interpretation
        )
        if earliest_candidate_gate_pass_start is None and gate_pass_candidate_starts:
            failures.append("research manifest earliest_candidate_gate_pass_start is null despite gate-pass candidate decisions")
        if earliest_candidate_gate_pass_start is not None:
            matching_decisions = [
                item for item in candidate_decisions
                if isinstance(item, dict)
                and item.get("candidate_start") == earliest_candidate_gate_pass_start
                and item.get("promotion_interpretation") == pass_interpretation
            ]
            if len(matching_decisions) != 1:
                failures.append("research manifest earliest_candidate_gate_pass_start does not match exactly one gate-pass candidate decision")
            elif gate_pass_candidate_starts and earliest_candidate_gate_pass_start != gate_pass_candidate_starts[0]:
                failures.append("research manifest earliest_candidate_gate_pass_start is not the earliest gate-pass candidate")
        refined_gate_pass_boundaries = sorted(
            item.get("refined_earliest_passing_snapshot") for item in candidate_decisions
            if isinstance(item, dict)
            and item.get("refined_earliest_passing_snapshot")
        )
        refined_candidate_rows_present = any(
            isinstance(item, dict) and "refined_earliest_passing_snapshot" in item
            for item in candidate_decisions
        )
        if refined_candidate_rows_present and "refined_earliest_candidate_gate_pass_boundary" not in research_manifest:
            failures.append(
                "research manifest refined_earliest_candidate_gate_pass_boundary is missing despite refined candidate row evidence"
            )
        if refined_earliest_candidate_gate_pass_boundary is None and refined_gate_pass_boundaries:
            failures.append("research manifest refined_earliest_candidate_gate_pass_boundary is null despite refined gate-pass candidate boundaries")
        if refined_earliest_candidate_gate_pass_boundary is not None:
            if not refined_gate_pass_boundaries:
                failures.append("research manifest refined_earliest_candidate_gate_pass_boundary is set without refined gate-pass candidate boundaries")
            elif refined_earliest_candidate_gate_pass_boundary != refined_gate_pass_boundaries[0]:
                failures.append("research manifest refined_earliest_candidate_gate_pass_boundary is not the earliest refined gate-pass boundary")
        recommended_interval = research_manifest.get("candidate_recommended_research_interval")
        if not isinstance(recommended_interval, dict):
            failures.append("research manifest candidate_recommended_research_interval is missing or not an object")
        else:
            expected_recommendation_status = (
                "CANDIDATE_REFINED_BOUNDARY_AVAILABLE"
                if refined_earliest_candidate_gate_pass_boundary
                else "NO_REFINED_BOUNDARY"
            )
            if recommended_interval.get("status") != expected_recommendation_status:
                failures.append("research manifest candidate_recommended_research_interval.status does not match refined boundary availability")
            if recommended_interval.get("start") != refined_earliest_candidate_gate_pass_boundary:
                failures.append("research manifest candidate_recommended_research_interval.start does not match refined boundary")
            if not isinstance(recommended_interval.get("end"), str):
                failures.append("research manifest candidate_recommended_research_interval.end is missing or not a string")
            if recommended_interval.get("profile") != PROFILE_ID:
                failures.append("research manifest candidate_recommended_research_interval.profile is not the published profile")
            if recommended_interval.get("profile_version") != PROFILE_VERSION:
                failures.append("research manifest candidate_recommended_research_interval.profile_version is not the published profile version")
            if recommended_interval.get("promotion_status") != "NOT_PROMOTED_UNLESS_PRESENT_IN_RESEARCH_QUALITY_INTERVALS":
                failures.append("research manifest candidate_recommended_research_interval.promotion_status is not fail-closed")

    policy = research_manifest.get("known_policy") or {}
    expected_policy = {
        "signals": SIGNAL_POLICY,
        "execution": EXECUTION_POLICY,
        "terminal_values": TERMINAL_VALUE_POLICY,
    }
    for key, expected in expected_policy.items():
        if policy.get(key) != expected:
            failures.append(f"known_policy.{key} is not the published downstream contract")
    expected_contract_fields = {
        "required_quality_threshold": REQUIRED_QUALITY_THRESHOLD,
        "recommended_signal_price_series": RECOMMENDED_SIGNAL_PRICE_SERIES,
        "raw_execution_price_artifact": RAW_EXECUTION_PRICE_ARTIFACT,
        "liquidity_artifact": LIQUIDITY_ARTIFACT,
        "top_liquidity_ranking_metric": TOP_LIQUIDITY_RANKING_METRIC,
        "terminal_value_policy_requirement": TERMINAL_VALUE_POLICY_REQUIREMENT,
    }
    for key, expected in expected_contract_fields.items():
        if research_manifest.get(key) != expected:
            failures.append(f"research manifest {key} is not {expected}")
    if research_manifest.get("liquid_v1_definition") != LIQUID_V1_DEFINITION:
        failures.append("research manifest liquid_v1_definition is not the published LIQUID_V1 contract")
    required_numeric_metrics = (
        "required_research_securities",
        "candidate_required_research_securities",
        "liquid_v1_securities",
        "candidate_liquid_v1_securities",
        "identity_failures",
        "material_price_action_missing_factors",
        "material_price_action_unresolved_boundaries",
    )
    for key in required_numeric_metrics:
        if not isinstance(research_manifest.get(key), int):
            failures.append(f"research manifest {key} is missing or not an integer")
    if (
        isinstance(research_manifest.get("candidate_required_research_securities"), int)
        and isinstance(research_manifest.get("required_research_securities"), int)
        and research_manifest["candidate_required_research_securities"] < research_manifest["required_research_securities"]
    ):
        failures.append("research manifest candidate_required_research_securities is smaller than required_research_securities")
    if (
        isinstance(research_manifest.get("candidate_liquid_v1_securities"), int)
        and isinstance(research_manifest.get("liquid_v1_securities"), int)
        and research_manifest["candidate_liquid_v1_securities"] < research_manifest["liquid_v1_securities"]
    ):
        failures.append("research manifest candidate_liquid_v1_securities is smaller than liquid_v1_securities")
    for key in ("identity_failures", "material_price_action_missing_factors", "material_price_action_unresolved_boundaries"):
        if isinstance(research_manifest.get(key), int) and research_manifest[key] != 0:
            failures.append(f"research manifest {key} is not zero")

    artifacts = research_manifest.get("artifacts") or {}
    for name in RESEARCH_MANIFEST_ARTIFACTS:
        if name not in artifacts:
            failures.append(f"research manifest artifact hash missing for {name}")
    monthly_contract = {
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

    for key in (
        "config_sha256",
        "manual_override_sha256",
        "partitioned_artifacts_manifest_sha256",
        "research_invariant_validation_sha256",
        "candidate_promotion_audit_sha256",
        "test_result_sha256",
        "ci_status_sha256",
    ):
        digest = research_manifest.get(key)
        if not is_sha256_digest(digest):
            failures.append(f"research manifest {key} is missing or invalid")
    for key in ("config_sha256", "manual_override_sha256"):
        if research_manifest.get(key) != manifest.get(key):
            failures.append(f"research manifest {key} does not match data manifest")
    quality_reports = research_manifest.get("quality_reports") or {}
    if not quality_reports:
        failures.append("research manifest quality_reports are missing")
    for name in REQUIRED_RESEARCH_REPORTS:
        if name not in quality_reports:
            failures.append(f"research manifest quality report hash missing for {name}")
        elif not is_sha256_digest(quality_reports.get(name)):
            failures.append(f"research manifest quality report hash for {name} is invalid")
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
    manifest = json.loads((release / DATA_RELEASE_MANIFEST_ARTIFACT).read_text(encoding="utf-8"))
    research_manifest_path = release / RESEARCH_RELEASE_MANIFEST_ARTIFACT
    research_manifest = json.loads(research_manifest_path.read_text(encoding="utf-8")) if research_manifest_path.exists() else {}
    promoted_research_start = (
        (research_manifest.get("research_quality") or {}).get("start")
        or (manifest.get("research_coverage") or {}).get("research_verified_start")
        or RESEARCH_START_DATE
    )
    missing = [name for name in REQUIRED if not (release / name).exists()]
    missing_reports = [name for name in REQUIRED_RESEARCH_REPORTS if not (report_dir / name).exists()]
    validation_report = report_dir / f"research_invariant_validation_{release.name}.json"
    if not validation_report.exists():
        missing_reports.append(validation_report.name)
    candidate_promotion_audit_report = report_dir / f"candidate_promotion_audit_{release.name}.json"
    if not candidate_promotion_audit_report.exists():
        missing_reports.append(candidate_promotion_audit_report.name)
    test_result_report = report_dir / f"test_results_{release.name}.xml"
    if not test_result_report.exists():
        missing_reports.append(test_result_report.name)
    ci_status_report = report_dir / f"ci_status_{release.name}.json"
    if research_manifest.get("ci_status_sha256") and not ci_status_report.exists():
        missing_reports.append(ci_status_report.name)
    partition_manifest_path = release / PARTITIONED_ARTIFACTS_MANIFEST
    manifest_mismatch = manifest.get("release_id") != release.name
    research_quality_ok = research_manifest.get("research_quality", {}).get("status") == RESEARCH_HIGH_CONFIDENCE_STATUS
    data_contract_failures = data_manifest_contract_failures(release, manifest)
    research_contract_failures = research_manifest_contract_failures(release, manifest, research_manifest)
    if missing or missing_reports or manifest_mismatch or not research_quality_ok or data_contract_failures or research_contract_failures:
        rows = [f"# Release completion audit: `{manifest.get('release_id')}`", "", "## Required artifact checks", ""]
        rows.extend(f"- {'PASS' if name not in missing else 'FAIL'}: `{name}`" for name in REQUIRED)
        if manifest_mismatch:
            rows.extend(["", f"- FAIL: manifest release_id does not match directory `{release.name}`"])
        if not research_quality_ok:
            rows.extend(["", f"- FAIL: research quality is not {RESEARCH_HIGH_CONFIDENCE_STATUS}"])
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
        if not is_sha256_digest(expected) or not path.is_file() or sha256(path) != expected:
            hash_mismatches.append(key)
    for name, expected in research_manifest.get("artifacts", {}).items():
        path = release / name
        if not is_sha256_digest(expected) or not path.is_file() or sha256(path) != expected:
            hash_mismatches.append(f"research/{name}")
    for name, expected in research_manifest.get("quality_reports", {}).items():
        path = report_dir / name
        if not is_sha256_digest(expected) or not path.is_file() or sha256(path) != expected:
            hash_mismatches.append(f"report/{name}")
    validation_expected = research_manifest.get("research_invariant_validation_sha256")
    validation_path = report_dir / f"research_invariant_validation_{release.name}.json"
    if validation_expected and (not is_sha256_digest(validation_expected) or not validation_path.is_file() or sha256(validation_path) != validation_expected):
        hash_mismatches.append(f"report/{validation_path.name}")
    candidate_expected = research_manifest.get("candidate_promotion_audit_sha256")
    if candidate_expected and (not is_sha256_digest(candidate_expected) or not candidate_promotion_audit_report.is_file() or sha256(candidate_promotion_audit_report) != candidate_expected):
        hash_mismatches.append(f"report/{candidate_promotion_audit_report.name}")
    test_expected = research_manifest.get("test_result_sha256")
    if test_expected and (not is_sha256_digest(test_expected) or not test_result_report.is_file() or sha256(test_result_report) != test_expected):
        hash_mismatches.append(f"report/{test_result_report.name}")
    ci_expected = research_manifest.get("ci_status_sha256")
    if ci_expected and (not is_sha256_digest(ci_expected) or not ci_status_report.is_file() or sha256(ci_status_report) != ci_expected):
        hash_mismatches.append(f"report/{ci_status_report.name}")
    partition_expected = research_manifest.get("partitioned_artifacts_manifest_sha256")
    if partition_expected and (not is_sha256_digest(partition_expected) or not partition_manifest_path.is_file() or sha256(partition_manifest_path) != partition_expected):
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
    candidate_promotion_summary = json.loads(candidate_promotion_audit_report.read_text(encoding="utf-8"))
    candidate_audit_summary = candidate_promotion_audit_summary(candidate_promotion_summary)
    candidate_manifest_audit_failures = candidate_manifest_audit_consistency_failures(research_manifest, candidate_promotion_summary)
    candidate_audits = candidate_promotion_summary.get("candidate_audits") or []
    missing_candidate_starts = candidate_audit_summary["missing_candidate_starts"]
    unexpected_candidate_starts = candidate_audit_summary["unexpected_candidate_starts"]
    duplicate_candidate_starts = candidate_audit_summary["duplicate_candidate_starts"]
    malformed_candidate_audits = candidate_audit_summary["malformed_candidate_audits"]
    malformed_candidate_report = candidate_audit_summary["malformed_candidate_report"]
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

    status_path = release / TRADING_STATUS_INTERVALS_ARTIFACT
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
        suspended_count = count(TRADING_STATUS_INTERVALS_ARTIFACT, "trading_status = 'SUSPENDED'")

    quality = {}
    missing_adjusted_contract = []
    adjusted = release / ADJUSTED_PRICE_ARTIFACT
    if adjusted.exists():
        quality = dict(con.execute("SELECT total_return_quality, count(*) FROM read_parquet(?) GROUP BY 1", [str(adjusted)]).fetchall())
        adjusted_columns = {row[0] for row in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(adjusted)]).fetchall()}
        missing_adjusted_contract = sorted({"price_return_adjusted_close", "total_return_adjusted_close"} - adjusted_columns)
    liquidity_window_failures = con.execute("""
        SELECT COUNT(*) FROM read_parquet(?)
        WHERE liquidity_window_definition IS DISTINCT FROM 'OFFICIAL_NSE_SESSION_WINDOW'
    """, [str(release / "liquidity_features.parquet")]).fetchone()[0]
    boundary_path = release / CORPORATE_ACTION_BOUNDARY_ARTIFACT
    boundary_quality = {}
    unresolved_required_boundaries = 0
    if boundary_path.exists():
        boundary_quality = dict(con.execute("SELECT validation_status, count(*) FROM read_parquet(?) GROUP BY 1", [str(boundary_path)]).fetchall())
        unresolved_required_boundaries = con.execute("""
            WITH promoted_required AS (
                SELECT DISTINCT security_id
                FROM read_parquet(?)
                WHERE CAST(date AS DATE) >= CAST(? AS DATE)
                  AND (NSE_BROAD_LIQUID_PIT_V1_eligible OR top750_liquidity)
            )
            SELECT COUNT(DISTINCT v.event_id)
            FROM read_parquet(?) v
            JOIN promoted_required q USING (security_id)
            WHERE CAST(v.ex_date AS DATE) >= CAST(? AS DATE)
              AND v.validation_status IN (
                'WARNING_LARGE_BOUNDARY_MOVE',
                'INVALID_PRE_EVENT_PRICE',
                'NO_BOUNDARY_OBSERVATIONS',
                'NO_LOCAL_BOUNDARY_OBSERVATION'
              )
        """, [str(release / RESEARCH_UNIVERSE_MONTHLY_ARTIFACT), promoted_research_start, str(boundary_path), promoted_research_start]).fetchone()[0]

    rows = [
        f"# Release completion audit: `{manifest['release_id']}`",
        "",
        "## Proven facts",
        "",
        f"- Coverage: `{manifest.get('coverage', {}).get('observed_start')}` through `{manifest.get('coverage', {}).get('observed_end')}`.",
        f"- Official daily observations: {count('daily_prices_raw.parquet'):,}.",
        f"- Canonical security-master rows: {count(SECURITY_MASTER_ARTIFACT):,}.",
        f"- Issuers: {count('issuer_master.parquet'):,}.",
        f"- Listing episodes: {count('listing_episodes.parquet'):,}.",
        f"- Corporate-action rows: {count(CORPORATE_ACTIONS_ARTIFACT):,}.",
        f"- Terminal-event rows: {count(TERMINAL_EVENTS_ARTIFACT):,}.",
        f"- Status intervals: {count(TRADING_STATUS_INTERVALS_ARTIFACT) if status_path.exists() else 'not published':,}." if status_path.exists() else "- Status intervals: not published.",
        f"- Suspended intervals: {suspended_count:,}." if suspended_count is not None else "- Suspended intervals: not measured.",
        f"- Status interval overlaps: {overlap_count:,}." if overlap_count is not None else "- Status interval overlaps: not measured.",
        f"- Adjusted-price quality counts: `{json.dumps(quality, sort_keys=True)}`.",
        f"- Adjusted-price contract missing columns: `{missing_adjusted_contract}`.",
        f"- Liquidity feature rows with non-official session window: {liquidity_window_failures:,}.",
        f"- Corporate-action boundary validation: `{json.dumps(boundary_quality, sort_keys=True)}`." if boundary_path.exists() else "- Corporate-action boundary validation: not published.",
        f"- Unresolved required material price-action boundaries: {unresolved_required_boundaries:,}.",
        f"- RAW integrity validation: `{json.dumps(raw_summary, sort_keys=True)}`.",
        f"- Source coverage validation: `{json.dumps(source_summary, sort_keys=True)}`.",
        f"- Research invariant validation: `{json.dumps(invariant_summary, sort_keys=True)}`.",
        f"- Candidate promotion audits: `{json.dumps(candidate_audit_summary, sort_keys=True)}`.",
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
        failures.append(f"research release is not {RESEARCH_HIGH_CONFIDENCE_STATUS}")
    failures.extend(data_contract_failures)
    failures.extend(research_contract_failures)
    failures.extend(f"missing required research report: {name}" for name in missing_reports)
    if invariant_summary["status"] != "PASS" or invariant_summary["failure_count"]:
        failures.append(f"research invariant validation is not clean: {json.dumps(invariant_summary, sort_keys=True)}")
    if missing_candidate_starts or unexpected_candidate_starts or duplicate_candidate_starts or malformed_candidate_audits or malformed_candidate_report:
        failures.append(f"candidate promotion audit evidence is incomplete: {json.dumps({'missing_candidate_starts': missing_candidate_starts, 'unexpected_candidate_starts': unexpected_candidate_starts, 'duplicate_candidate_starts': duplicate_candidate_starts, 'malformed_candidate_audits': malformed_candidate_audits, 'malformed_candidate_report': malformed_candidate_report}, sort_keys=True)}")
    failures.extend(candidate_manifest_audit_failures)
    if source_summary["status"] != "PASS":
        failures.append(f"source coverage validation is not clean: {json.dumps(source_summary, sort_keys=True)}")
    if raw_summary["status"] != "PASS":
        failures.append(f"RAW integrity validation is not clean: {json.dumps(raw_summary, sort_keys=True)}")
    if missing_adjusted_contract:
        failures.append(f"adjusted-price artifact is missing contract columns: {missing_adjusted_contract}")
    if liquidity_window_failures:
        failures.append(f"liquidity features are not all official-session windows: {liquidity_window_failures}")
    if unresolved_required_boundaries:
        failures.append(f"unresolved material price-action boundaries remain in required research scope: {unresolved_required_boundaries}")
    if test_summary["tests"] <= 0 or test_summary["failures"] or test_summary["errors"]:
        failures.append(f"test result report is not clean: {json.dumps(test_summary, sort_keys=True)}")
    if not test_summary["model_arena_handoff_passed"]:
        failures.append("Model Arena handoff smoke test did not pass in release evidence")
    if not test_summary["multi_era_source_fixture_passed"]:
        failures.append("multi-era source fixture smoke test did not pass in release evidence")
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
        f"- The complete 2006 onward archive is exploratory unless covered by a manifest research-quality interval; the scoped `{promoted_research_start}` onward research universe is RESEARCH_HIGH_CONFIDENCE.",
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
