from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

COMMANDS = [
    "download-nse-history", "download-nse-reference-data", "normalize-market-data",
    "build-security-master", "resolve-identities", "build-listing-episodes",
    "build-corporate-actions", "build-raw-prices", "build-adjusted-prices",
    "build-active-universe", "build-liquidity-features", "build-source-release",
    "build-candidate-promotion-audits", "candidate-readiness", "audit-data", "publish-release", "build",
]
CORE_SOURCE_STAGES = {
    "build-security-master", "resolve-identities", "build-listing-episodes",
    "build-raw-prices", "build-active-universe", "build-liquidity-features",
}


def main() -> None:
    parser = argparse.ArgumentParser(prog="india-equity-data")
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--root", default=".")
    parser.add_argument("--raw", default="data/raw/nse/bhavcopy")
    parser.add_argument("--corporate-actions", default="data/raw/nse/corporate_actions/corporate_actions_2006_2026.json")
    parser.add_argument("--adjusted-out", default="data/derived/daily_prices_adjusted.parquet")
    parser.add_argument("--release-id")
    parser.add_argument("--candidate-start")
    parser.add_argument("--source-release")
    parser.add_argument("--terminal-events")
    parser.add_argument("--suspension-events", default="data/derived/suspension_events_resolved_v1.parquet")
    parser.add_argument("--ci-run-id")
    parser.add_argument("--ci-status-report")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    root = Path(args.root)
    if args.start:
        date.fromisoformat(args.start)
    if args.end:
        date.fromisoformat(args.end)
    def audit_release(release_id: str) -> None:
        release = root / "releases" / release_id
        if not release.exists():
            raise SystemExit(f"Release directory does not exist: {release}")
        output = root / "reports" / f"completion_audit_{release_id}.md"
        command = [sys.executable, str(root / "scripts/build_completion_audit.py"), "--release", str(release), "--out", str(output)]
        if args.dry_run:
            print(" ".join(command))
            return
        subprocess.run(command, check=True, cwd=root)

    if args.command == "download-nse-history":
        command = [str(root / "scripts/download_nse_history.sh"), args.start or "2006-01-01", args.end or date.today().isoformat(), str(root / args.raw)]
        if args.dry_run:
            print(" ".join(command))
            return
        subprocess.run(command, check=True, cwd=root)
    elif args.command == "build-corporate-actions":
        command = [sys.executable, str(root / "scripts/normalize_corporate_actions.py"), "--raw", str(root / args.corporate_actions), "--master", str(root / "data/canonical/security_master.jsonl"), "--out", str(root / "data/canonical/corporate_actions.jsonl")]
        if args.dry_run:
            print(" ".join(command))
            return
        subprocess.run(command, check=True, cwd=root)
    elif args.command == "build-adjusted-prices":
        prices = root / "data/canonical/daily_prices_raw.jsonl"
        events = root / "data/canonical/corporate_actions.jsonl"
        if not prices.exists() or not events.exists():
            raise SystemExit("build-adjusted-prices requires canonical raw prices and corporate actions")
        command = [sys.executable, str(root / "scripts/apply_corporate_action_adjustments.py"), "--prices", str(prices), "--events", str(events), "--out", str(root / args.adjusted_out)]
        if args.dry_run:
            print(" ".join(command))
            return
        subprocess.run(command, check=True, cwd=root)
    elif args.command == "build-source-release":
        if not args.release_id or not args.terminal_events:
            raise SystemExit("build-source-release requires --release-id and --terminal-events")
        command = [sys.executable, str(root / "scripts/build_source_release.py"), "--root", str(root), "--release-id", args.release_id, "--terminal-events", args.terminal_events, "--suspension-events", args.suspension_events, "--raw", args.raw, "--corporate-actions", args.corporate_actions]
        if args.start:
            command.extend(["--start", args.start])
        if args.end:
            command.extend(["--end", args.end])
        if args.ci_run_id:
            command.extend(["--ci-run-id", args.ci_run_id])
        if args.ci_status_report:
            command.extend(["--ci-status-report", args.ci_status_report])
        if args.dry_run:
            print(" ".join(command))
            return
        subprocess.run(command, check=True, cwd=root)
    elif args.command in CORE_SOURCE_STAGES or args.command == "normalize-market-data":
        command = [sys.executable, str(root / "scripts/build_nse_universe.py"), "--raw", str(root / args.raw), "--out", str(root / "data"), "--manual-overrides", str(root / "data/reference/manual_identity_overrides.yaml")]
        if args.start:
            command.extend(["--start", args.start])
        if args.end:
            command.extend(["--end", args.end])
        if args.dry_run:
            print(" ".join(command))
            return
        if args.command in CORE_SOURCE_STAGES:
            print(f"Stage '{args.command}' uses the coupled NSE source builder")
        subprocess.run(command, check=True, cwd=root)
    elif args.command == "audit-data":
        if not args.release_id:
            raise SystemExit("audit-data requires --release-id")
        audit_release(args.release_id)
    elif args.command == "candidate-readiness":
        if not args.release_id:
            raise SystemExit("candidate-readiness requires --release-id")
        from .api import DataPlatform
        platform = DataPlatform.from_release(root / "releases" / args.release_id, strict=False)
        if args.candidate_start:
            candidate_decision = platform.candidate_promotion_decision(args.candidate_start)
            refined_boundary = platform.refined_earliest_candidate_gate_pass_boundary()
            output = {
                "release_id": args.release_id,
                "quality_tier": platform.quality_tier,
                "coverage_start": platform.coverage_start.isoformat() if platform.coverage_start else None,
                "coverage_end": platform.coverage_end.isoformat() if platform.coverage_end else None,
                "verified_start": platform.verified_start.isoformat() if platform.verified_start else None,
                "verified_end": platform.verified_end.isoformat() if platform.verified_end else None,
                "candidate_start": args.candidate_start,
                "candidate_decision": candidate_decision,
                "candidate_feature_readiness": candidate_decision.get("feature_readiness"),
                "candidate_refined_earliest_passing_snapshot": candidate_decision.get("refined_earliest_passing_snapshot"),
                "refined_earliest_candidate_gate_pass_boundary": (
                    refined_boundary.isoformat()
                    if refined_boundary
                    else None
                ),
                "candidate_gate_pass_ready": platform.candidate_gate_pass_ready(args.candidate_start),
                "research_quality_status": platform.research_quality_on(args.candidate_start),
                "candidate_research_ready": platform.candidate_research_ready(args.candidate_start),
            }
        else:
            output = {
                "release_id": args.release_id,
                "quality_tier": platform.quality_tier,
                "coverage_start": platform.coverage_start.isoformat() if platform.coverage_start else None,
                "coverage_end": platform.coverage_end.isoformat() if platform.coverage_end else None,
                "verified_start": platform.verified_start.isoformat() if platform.verified_start else None,
                "verified_end": platform.verified_end.isoformat() if platform.verified_end else None,
                "candidate_promotion_summary": platform.candidate_promotion_summary(),
            }
        print(json.dumps(output, indent=2, sort_keys=True))
    elif args.command == "build-candidate-promotion-audits":
        if not args.release_id:
            raise SystemExit("build-candidate-promotion-audits requires --release-id")
        release = root / "releases" / args.release_id
        output = root / "reports" / f"candidate_promotion_audit_{args.release_id}.json"
        command = [
            sys.executable,
            str(root / "scripts/build_candidate_promotion_audits.py"),
            "--release",
            str(release),
            "--out",
            str(output),
        ]
        if args.start:
            command.extend(["--control-start", args.start])
        if args.dry_run:
            print(" ".join(command))
            return
        subprocess.run(command, check=True, cwd=root)
    elif args.command == "publish-release":
        if not args.release_id:
            raise SystemExit("publish-release requires --release-id")
        audit_release(args.release_id)
        print(f"Release audit complete: {root / 'releases' / args.release_id}")
    elif args.command == "build":
        for layer in ("data/raw", "data/normalized", "data/canonical", "data/derived", "releases", "reports"):
            (root / layer).mkdir(parents=True, exist_ok=True)
        if args.source_release:
            if not args.release_id:
                raise SystemExit("build with --source-release requires --release-id")
            command = [sys.executable, str(root / "scripts/build_cached_release.py"), "--root", str(root), "--source-release", args.source_release, "--release-id", args.release_id]
            if args.dry_run:
                print(" ".join(command))
                return
            subprocess.run(command, check=True, cwd=root)
            audit_release(args.release_id)
        elif args.release_id and (root / "releases" / args.release_id).exists():
            audit_release(args.release_id)
        elif args.start or args.end:
            if args.release_id:
                raise SystemExit("source-driven build creates intermediates only; use --source-release to publish a release")
            command = [sys.executable, str(root / "scripts/build_nse_universe.py"), "--raw", str(root / args.raw), "--out", str(root / "data"), "--manual-overrides", str(root / "data/reference/manual_identity_overrides.yaml")]
            if args.start:
                command.extend(["--start", args.start])
            if args.end:
                command.extend(["--end", args.end])
            if args.dry_run:
                print(" ".join(command))
                return
            subprocess.run(command, check=True, cwd=root)
            print("Source-driven intermediate build complete; no release was published")
        else:
            raise SystemExit("build requires --source-release and --release-id, or an existing --release-id")
    else:
        raise SystemExit(f"Stage '{args.command}' is not implemented by the current source adapter")


if __name__ == "__main__":
    main()
