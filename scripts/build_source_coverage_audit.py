#!/usr/bin/env python3
"""Audit source dates against the published official-observation calendar."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--manifest", default="data/raw/manifests/source_manifest.json")
    parser.add_argument("--out", default="reports/data_source_coverage.md")
    args = parser.parse_args()

    release = Path(args.release)
    manifest_path = Path(args.manifest)
    entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    dates = [str(row["source_date"]) for row in entries if row.get("download_status") == "DOWNLOADED_VALID_ARCHIVE"]
    invalid = [row for row in entries if row.get("download_status") != "DOWNLOADED_VALID_ARCHIVE"]
    duplicate_dates = sorted({date for date in dates if dates.count(date) > 1})

    connection = duckdb.connect()
    try:
        calendar_path = (release / "trading_calendar.parquet").resolve()
        calendar = {str(row[0]) for row in connection.execute(
            f"SELECT DISTINCT CAST(date AS DATE) FROM read_parquet('{calendar_path}')"
        ).fetchall()}
    finally:
        connection.close()

    source_dates = set(dates)
    missing = sorted(calendar - source_dates)
    extra = sorted(source_dates - calendar)
    passed = not missing and not extra and not invalid and not duplicate_dates
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join([
        "# Data source coverage",
        "",
        "The expected session set is the date set in `trading_calendar.parquet`.",
        "This is an archive integrity audit. It does not claim an independent exchange calendar.",
        "",
        f"- Manifest entries: `{len(entries):,}`.",
        f"- Valid archive entries: `{len(dates):,}`.",
        f"- Duplicate source dates: `{len(duplicate_dates):,}`.",
        f"- Expected official sessions: `{len(calendar):,}`.",
        f"- Missing expected source dates: `{len(missing):,}`.",
        f"- Unexpected source dates: `{len(extra):,}`.",
        f"- Invalid or failed manifest entries: `{len(invalid):,}`.",
        "",
        f"Source integrity gate: `{'PASS' if passed else 'FAIL'}`.",
        "",
        "## Missing expected dates",
        "",
        ", ".join(f"`{date}`" for date in missing) if missing else "None.",
        "",
        "## Unexpected dates",
        "",
        ", ".join(f"`{date}`" for date in extra) if extra else "None.",
        "",
        "Retrieval timestamps use local file modification time when the original HTTP timestamp is not available.",
    ]) + "\n", encoding="utf-8")
    print(json.dumps({"expected": len(calendar), "valid": len(dates), "missing": len(missing), "unexpected": len(extra), "invalid": len(invalid)}, sort_keys=True))


if __name__ == "__main__":
    main()
