from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from india_active_universe.profiles import ACTIVE_DEFINITION, COMPONENT_QUALITY, DATASET_QUALITY_TIER, DATA_RELEASE_MANIFEST_ARTIFACT, PARSER_VERSIONS, PRIORITY_SCOPE, PROFILE_ID, PROFILE_VERSION, RESEARCH_START_DATE, SOURCE_BUILD_MODE, SOURCE_MANIFEST_ARTIFACT, SUSPENSION_SOURCE_MANIFEST_ARTIFACT, TARGET_RELEASE_ID


def rows(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def current_commit(root: Path) -> str:
    try:
        return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="data")
    parser.add_argument("--release-id", default=TARGET_RELEASE_ID)
    parser.add_argument("--release-dir")
    parser.add_argument("--reports-dir")
    parser.add_argument("--config")
    args = parser.parse_args()
    root = Path(args.root)
    prices_path = root / "canonical/daily_prices_raw.jsonl"
    universe_path = root / "derived/active_universe_daily.jsonl"
    master_path = root / "canonical/security_master.jsonl"
    first = last = None
    price_rows = 0
    securities = set()
    year_counts: Counter[str] = Counter()
    for row in rows(prices_path):
        point = row["date"]
        first = point if first is None or point < first else first
        last = point if last is None or point > last else last
        price_rows += 1
        securities.add(row["security_id"])
    for row in rows(universe_path):
        year_counts[row["date"][:4]] += 1
    master_rows = list(rows(master_path))
    quality_counts = Counter(row.get("identity_quality", "UNKNOWN") for row in master_rows)
    source_manifest = root / "raw/manifests/source_manifest.json"
    config_path = Path(args.config) if args.config else root.parent / "config/default.yaml"
    release_dir = Path(args.release_dir) if args.release_dir else root.parent / "releases" / args.release_id
    reports = Path(args.reports_dir) if args.reports_dir else root.parent / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "security_coverage.md").write_text("# Security coverage\n\n" + f"- Observations: {price_rows:,}\n- Canonical security IDs: {len(securities):,}\n- Covered dates: {first} through {last}\n- Master rows: {len(master_rows):,}\n\n## Active rows by year\n\n" + "\n".join(f"- {year}: {count:,}" for year, count in sorted(year_counts.items())) + "\n", encoding="utf-8")
    (reports / "security_identity_quality.md").write_text("# Security identity quality\n\n" + "\n".join(f"- {key}: {value:,}" for key, value in sorted(quality_counts.items())) + "\n", encoding="utf-8")
    (reports / "survivorship_audit.md").write_text("# Survivorship audit\n\nThis first release is observation-based. Securities are retained for every dated official observation, independent of whether they appear in the current NSE reference universe. Terminal-event classification remains a subsequent evidence-enrichment stage.\n", encoding="utf-8")
    artifacts = {}
    if source_manifest.exists():
        release_source_manifest = release_dir / SOURCE_MANIFEST_ARTIFACT
        if not release_source_manifest.exists():
            release_source_manifest.write_bytes(source_manifest.read_bytes())
        artifacts[f"release/{SOURCE_MANIFEST_ARTIFACT}"] = file_hash(release_source_manifest)
    suspension_manifest = root / "raw/nse/notices/suspensions/source_manifest.json"
    if suspension_manifest.exists():
        release_suspension_manifest = release_dir / SUSPENSION_SOURCE_MANIFEST_ARTIFACT
        if not release_suspension_manifest.exists():
            release_suspension_manifest.write_bytes(suspension_manifest.read_bytes())
        artifacts[f"release/{SUSPENSION_SOURCE_MANIFEST_ARTIFACT}"] = file_hash(release_suspension_manifest)
    if release_dir.exists():
        for path in sorted(item for item in release_dir.iterdir() if item.is_file() and item.name != DATA_RELEASE_MANIFEST_ARTIFACT and item.suffix in {".parquet", ".json"}):
            artifacts[f"release/{path.name}"] = file_hash(path)
    manual_override_path = root.parents[2] / "data/reference/manual_identity_overrides.yaml"
    manifest = {"release_id": args.release_id, "project_id": "india-active-universe", "git_commit": current_commit(root), "build_mode": SOURCE_BUILD_MODE, "coverage": {"observed_start": first, "observed_end": last, "security_count": len(securities), "observation_count": price_rows}, "source_coverage": {"source_verified_start": first, "source_verified_end": last, "verification_basis": "official NSE market-data files; no independent exchange calendar claim"}, "research_coverage": {"research_verified_start": RESEARCH_START_DATE, "research_verified_end": last, "universe_profile": PROFILE_ID, "profile_version": PROFILE_VERSION, "priority_scope": PRIORITY_SCOPE}, "component_quality": COMPONENT_QUALITY, "definition": ACTIVE_DEFINITION, "quality_tier": DATASET_QUALITY_TIER, "verified_start_date": first, "verified_end_date": last, "source_manifest_sha256": file_hash(source_manifest) if source_manifest.exists() else None, "config_sha256": file_hash(config_path) if config_path.exists() else None, "manual_override_sha256": file_hash(manual_override_path) if manual_override_path.exists() else None, "parser_versions": PARSER_VERSIONS, "artifacts": artifacts, "quality": {"identity_quality": dict(quality_counts), "quality_findings": 0}, "source": "NSE_OFFICIAL_BHAVCOPY"}
    release_dir.mkdir(parents=True, exist_ok=True)
    (release_dir / DATA_RELEASE_MANIFEST_ARTIFACT).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest["coverage"], sort_keys=True))


if __name__ == "__main__":
    main()
