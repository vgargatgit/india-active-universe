from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from .raw import ImmutableRawStore


COMMANDS = [
    "download-nse-history", "download-nse-reference-data", "normalize-market-data",
    "build-security-master", "resolve-identities", "build-listing-episodes",
    "build-corporate-actions", "build-raw-prices", "build-adjusted-prices",
    "build-active-universe", "build-liquidity-features", "audit-data", "publish-release", "build",
]


def main() -> None:
    parser = argparse.ArgumentParser(prog="india-equity-data")
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--root", default=".")
    parser.add_argument("--release-id")
    args = parser.parse_args()
    root = Path(args.root)
    if args.start:
        date.fromisoformat(args.start)
    if args.end:
        date.fromisoformat(args.end)
    if args.command == "build":
        for layer in ("data/raw", "data/normalized", "data/canonical", "data/derived", "releases", "reports"):
            (root / layer).mkdir(parents=True, exist_ok=True)
        print(f"Initialized deterministic build workspace at {root}")
    elif args.command == "publish-release":
        release_id = args.release_id or "india_equity_data_unreleased"
        print(f"Release {release_id} requires completed canonical and derived artifacts before publication")
    else:
        print(f"Stage '{args.command}' is available; source-specific adapters must be configured before execution")


if __name__ == "__main__":
    main()
