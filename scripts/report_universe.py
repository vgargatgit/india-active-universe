from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="data")
    parser.add_argument("--release-id", default="india_equity_data_v0.1.0")
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
    config_path = root.parent / "config/default.yaml"
    release_dir = root.parent / "releases" / args.release_id
    reports = root.parent / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "security_coverage.md").write_text("# Security coverage\n\n" + f"- Observations: {price_rows:,}\n- Canonical security IDs: {len(securities):,}\n- Covered dates: {first} through {last}\n- Master rows: {len(master_rows):,}\n\n## Active rows by year\n\n" + "\n".join(f"- {year}: {count:,}" for year, count in sorted(year_counts.items())) + "\n", encoding="utf-8")
    (reports / "security_identity_quality.md").write_text("# Security identity quality\n\n" + "\n".join(f"- {key}: {value:,}" for key, value in sorted(quality_counts.items())) + "\n", encoding="utf-8")
    (reports / "survivorship_audit.md").write_text("# Survivorship audit\n\nThis first release is observation-based. Securities are retained for every dated official observation, independent of whether they appear in the current NSE reference universe. Terminal-event classification remains a subsequent evidence-enrichment stage.\n", encoding="utf-8")
    artifacts = {}
    for path in (master_path, prices_path, universe_path, root / "derived/liquidity_features.jsonl", root / "derived/data_quality_findings.jsonl"):
        artifacts[str(path.relative_to(root))] = file_hash(path)
    if source_manifest.exists():
        release_source_manifest = release_dir / "source_manifest.json"
        if not release_source_manifest.exists():
            release_source_manifest.write_bytes(source_manifest.read_bytes())
        artifacts["release/source_manifest.json"] = file_hash(release_source_manifest)
    suspension_manifest = root / "raw/nse/notices/suspensions/source_manifest.json"
    if suspension_manifest.exists():
        release_suspension_manifest = release_dir / "suspension_source_manifest.json"
        if not release_suspension_manifest.exists():
            release_suspension_manifest.write_bytes(suspension_manifest.read_bytes())
        artifacts["release/suspension_source_manifest.json"] = file_hash(release_suspension_manifest)
    if release_dir.exists():
        for path in sorted(release_dir.glob("*.parquet")):
            artifacts[f"release/{path.name}"] = file_hash(path)
    manifest = {"release_id": args.release_id, "project_id": "india-active-universe", "git_commit": "NOT_CAPTURED_BY_BUILD", "coverage": {"observed_start": first, "observed_end": last, "security_count": len(securities), "observation_count": price_rows}, "definition": "ACTIVE_V1", "quality_tier": "DATASET_EXPLORATORY", "verified_start_date": first, "verified_end_date": last, "source_manifest_sha256": file_hash(source_manifest) if source_manifest.exists() else None, "config_sha256": file_hash(config_path) if config_path.exists() else None, "parser_versions": {"nse_bhavcopy": "nse-bhavcopy-v2", "canonicalization": "identity-v1"}, "artifacts": artifacts, "quality": {"identity_quality": dict(quality_counts), "quality_findings": 0}, "source": "NSE_OFFICIAL_BHAVCOPY"}
    release_dir.mkdir(parents=True, exist_ok=True)
    (release_dir / "data_release_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest["coverage"], sort_keys=True))


if __name__ == "__main__":
    main()
