#!/usr/bin/env python3
"""Build a Parquet release from the immutable NSE cache and explicit evidence inputs."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from india_active_universe.profiles import (
    ADJUSTED_PRICE_ARTIFACT,
    CORPORATE_ACTION_BOUNDARY_ARTIFACT,
    CORPORATE_ACTIONS_ARTIFACT,
    LIQUIDITY_ARTIFACT,
    RAW_EXECUTION_PRICE_ARTIFACT,
    RESEARCH_START_DATE,
    SECURITY_MASTER_ARTIFACT,
    SOURCE_MANIFEST_ARTIFACT,
    SUSPENSION_EVENTS_ARTIFACT,
    TERMINAL_EVENTS_ARTIFACT,
    TRADING_CALENDAR_ARTIFACT,
    TRADING_STATUS_INTERVALS_ARTIFACT,
)


def run(root: Path, command: list[str], *, env: dict[str, str] | None = None) -> None:
    print("RUN", " ".join(command))
    subprocess.run(command, check=True, cwd=root, env=env)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--terminal-events", required=True)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--raw", default="data/raw/nse/bhavcopy")
    parser.add_argument("--corporate-actions", default="data/raw/nse/corporate_actions/corporate_actions_2006_2026.json")
    parser.add_argument("--suspension-events", default="data/derived/suspension_events_resolved_v1.parquet")
    parser.add_argument("--ci-run-id", help="GitHub Actions run ID to convert into release CI evidence.")
    parser.add_argument("--ci-status-report", help="Existing ci_status_<release_id>.json evidence file to copy into reports.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    release = root / "releases" / args.release_id
    work = root / "data/build" / args.release_id
    terminal = root / args.terminal_events
    suspension_events = root / args.suspension_events
    manual_overrides = root / "data/reference/manual_identity_overrides.yaml"
    source_manifest = root / "data/raw/manifests/source_manifest.json"
    if release.exists() or work.exists():
        raise SystemExit("release or build workspace already exists; immutable build target refused")
    if not terminal.is_file():
        raise SystemExit(f"terminal evidence file does not exist: {terminal}")
    if not suspension_events.is_file():
        raise SystemExit(f"suspension evidence file does not exist: {suspension_events}")
    if not manual_overrides.is_file():
        raise SystemExit(f"manual override file does not exist: {manual_overrides}")
    if not source_manifest.is_file():
        raise SystemExit(f"source manifest does not exist: {source_manifest}")
    if not args.dry_run and not args.ci_run_id and not args.ci_status_report:
        raise SystemExit("build-source-release requires --ci-run-id or --ci-status-report because v2.0 completion audit requires CI evidence")
    if args.ci_run_id and args.ci_status_report:
        raise SystemExit("provide only one of --ci-run-id or --ci-status-report")
    raw = root / args.raw
    corporate_actions = root / args.corporate_actions
    reports = root / "reports"
    ci_status_target = reports / f"ci_status_{args.release_id}.json"
    commands = []
    core = [sys.executable, str(root / "scripts/build_nse_universe.py"), "--raw", str(raw), "--out", str(work), "--manual-overrides", str(manual_overrides)]
    if args.start:
        core += ["--start", args.start]
    if args.end:
        core += ["--end", args.end]
    commands.append(core)
    raw_prices = release / RAW_EXECUTION_PRICE_ARTIFACT
    liquidity_features = release / LIQUIDITY_ARTIFACT
    commands.extend([
        [sys.executable, str(root / "scripts/publish_parquet.py"), "--data", str(work), "--release", str(release)],
        [sys.executable, str(root / "scripts/build_trading_calendar.py"), "--prices", str(raw_prices), "--out", str(release / TRADING_CALENDAR_ARTIFACT)],
        [sys.executable, str(root / "scripts/rebuild_liquidity_features_duckdb.py"), "--prices", str(raw_prices), "--calendar", str(release / TRADING_CALENDAR_ARTIFACT), "--out", str(liquidity_features)],
        [sys.executable, str(root / "scripts/publish_identity_artifacts.py"), "--master", str(work / "canonical/security_master.jsonl"), "--release", str(release)],
        [sys.executable, str(root / "scripts/normalize_corporate_actions.py"), "--raw", str(corporate_actions), "--master", str(work / "canonical/security_master.jsonl"), "--out", str(work / "canonical/corporate_actions.jsonl")],
        [sys.executable, str(root / "scripts/publish_corporate_actions.py"), "--input", str(work / "canonical/corporate_actions.jsonl"), "--out", str(work / "derived" / CORPORATE_ACTIONS_ARTIFACT)],
        [sys.executable, str(root / "scripts/publish_extensions.py"), "--data", str(work), "--release", str(release), "--corporate-actions", str(work / "derived" / CORPORATE_ACTIONS_ARTIFACT), "--terminal-events", str(terminal)],
        [sys.executable, str(root / "scripts/apply_corporate_action_adjustments.py"), "--prices", str(work / "canonical/daily_prices_raw.jsonl"), "--events", str(work / "canonical/corporate_actions.jsonl"), "--out", str(release / ADJUSTED_PRICE_ARTIFACT)],
        [sys.executable, str(root / "scripts/validate_corporate_action_boundaries.py"), "--events", str(release / CORPORATE_ACTIONS_ARTIFACT), "--prices", str(raw_prices), "--calendar", str(release / TRADING_CALENDAR_ARTIFACT), "--out", str(release / CORPORATE_ACTION_BOUNDARY_ARTIFACT)],
        [sys.executable, str(root / "scripts/build_status_intervals.py"), "--master", str(work / "canonical/security_master.jsonl"), "--terminal-events", str(release / TERMINAL_EVENTS_ARTIFACT), "--out", str(release / TRADING_STATUS_INTERVALS_ARTIFACT)],
        [sys.executable, str(root / "scripts/build_identity_history_artifacts.py"), "--master", str(release / SECURITY_MASTER_ARTIFACT), "--out-dir", str(release)],
        [sys.executable, str(root / "scripts/build_research_universe.py"), "--release", str(release), "--start", RESEARCH_START_DATE],
        [sys.executable, str(root / "scripts/build_partitioned_release_artifacts.py"), "--release", str(release)],
        [sys.executable, str(root / "scripts/report_universe.py"), "--root", str(work), "--release-id", args.release_id, "--release-dir", str(release), "--reports-dir", str(root / "reports"), "--config", str(root / "config/default.yaml")],
        [sys.executable, str(root / "scripts/validate_research_release.py"), "--release", str(release), "--out", str(root / "reports" / f"research_invariant_validation_{args.release_id}.json")],
        [sys.executable, "-m", "pytest", "-q", "--junitxml", str(root / "reports" / f"test_results_{args.release_id}.xml")],
        [sys.executable, str(root / "scripts/audit_raw_integrity.py"), "--root", str(raw), "--out", str(root / "reports" / "raw_integrity_audit.md")],
        [sys.executable, str(root / "scripts/build_source_coverage_audit.py"), "--release", str(release), "--manifest", str(source_manifest), "--out", str(root / "reports/data_source_coverage.md")],
        [sys.executable, str(root / "scripts/build_research_reports.py"), "--release", str(release), "--reports", str(root / "reports"), "--config", str(root / "config/default.yaml"), "--manual-overrides", str(root / "data/reference/manual_identity_overrides.yaml")],
        [sys.executable, str(root / "scripts/build_completion_audit.py"), "--release", str(release), "--out", str(root / "reports" / f"completion_audit_{args.release_id}.md")],
    ])
    if args.end:
        for command in commands:
            if command[1].endswith("build_research_universe.py"):
                command.extend(["--end", args.end])
                break
    status_index = next(index for index, command in enumerate(commands) if command[1].endswith("build_identity_history_artifacts.py"))
    commands.insert(status_index, [
        sys.executable, str(root / "scripts/build_verified_suspension_status.py"),
        "--events", str(suspension_events),
        "--master", str(release / SECURITY_MASTER_ARTIFACT),
        "--base-intervals", str(release / TRADING_STATUS_INTERVALS_ARTIFACT),
        "--prices", str(raw_prices),
        "--events-out", str(release / SUSPENSION_EVENTS_ARTIFACT),
        "--intervals-out", str(release / TRADING_STATUS_INTERVALS_ARTIFACT),
    ])
    if args.dry_run:
        for command in commands:
            print(" ".join(command))
        if args.ci_run_id:
            print(" ".join([sys.executable, str(root / "scripts/write_ci_status_report.py"), "--release", str(release), "--run-id", args.ci_run_id, "--out", str(ci_status_target)]))
        if args.ci_status_report:
            print(f"copy {root / args.ci_status_report} {ci_status_target}")
        return
    work.mkdir(parents=True)
    release.mkdir(parents=True)
    target = work / "raw/manifests" / SOURCE_MANIFEST_ARTIFACT
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_manifest, target)
    reports.mkdir(parents=True, exist_ok=True)
    for command in commands:
        if command[1].endswith("build_research_reports.py"):
            if args.ci_run_id:
                run(root, [sys.executable, str(root / "scripts/write_ci_status_report.py"), "--release", str(release), "--run-id", args.ci_run_id, "--out", str(ci_status_target)])
            elif args.ci_status_report:
                source_report = root / args.ci_status_report
                if not source_report.is_file():
                    raise SystemExit(f"CI status report does not exist: {source_report}")
                shutil.copy2(source_report, ci_status_target)
        command_env = None
        if command[:3] == [sys.executable, "-m", "pytest"]:
            command_env = os.environ.copy()
            command_env["INDIA_EQUITY_DATA_RELEASE_ID"] = args.release_id
        run(root, command, env=command_env)
    print(f"SOURCE_RELEASE_COMPLETE {release}")


if __name__ == "__main__":
    main()
