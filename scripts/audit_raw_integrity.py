#!/usr/bin/env python3
"""Audit every cached NSE bhavcopy with the download integrity validator."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from validate_nse_archive import validate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="data/raw/nse/bhavcopy")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    files = sorted(Path(args.root).glob("*.zip"))
    valid = []
    invalid = []
    dates = []
    for path in files:
        try:
            dates.append(date.fromisoformat(path.stem))
        except ValueError:
            invalid.append((path.name, "INVALID_DATE_FILENAME"))
            continue
        ok, reason = validate(path)
        (valid if ok else invalid).append((path.name, reason))
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# RAW integrity audit",
        "",
        f"- Root: `{args.root}`",
        f"- Files inspected: {len(files):,}",
        f"- Valid NSE market archives: {len(valid):,}",
        f"- Invalid files: {len(invalid):,}",
        f"- Earliest filename date: `{min(dates) if dates else None}`",
        f"- Latest filename date: `{max(dates) if dates else None}`",
        f"- RAW integrity gate: `{'PASS' if not invalid else 'FAIL'}`.",
        "",
        "## Invalid files",
        "",
    ]
    lines.extend(f"- `{name}`: {reason}" for name, reason in invalid)
    if not invalid:
        lines.append("- None")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"files={len(files)} valid={len(valid)} invalid={len(invalid)}")


if __name__ == "__main__":
    main()
