from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

COMMANDS = [
    "download-nse-history", "download-nse-reference-data", "normalize-market-data",
    "build-security-master", "resolve-identities", "build-listing-episodes",
    "build-corporate-actions", "build-raw-prices", "build-adjusted-prices",
    "build-active-universe", "build-liquidity-features", "audit-data", "publish-release", "build",
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
    parser.add_argument("--release-id")
    parser.add_argument("--source-release")
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
        else:
            raise SystemExit("build requires --source-release and --release-id, or an existing --release-id")
    else:
        raise SystemExit(f"Stage '{args.command}' is not implemented by the current source adapter")


if __name__ == "__main__":
    main()
