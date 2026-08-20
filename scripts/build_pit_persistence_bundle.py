from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import shutil
import tarfile
from pathlib import Path


CONTRACT = "pit-rebuild-persistence-v1"
CORPORATE_MANIFEST = "source_manifest.json"
CORPORATE_MERGED = "corporate_actions_2006_2026.json"
SUSPENSION_MANIFEST = "source_manifest.json"


class PersistenceError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def logical_sha256(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _find_unique(root: Path, filename: str) -> Path:
    direct = root / filename
    if direct.is_file():
        return direct
    matches = sorted(path for path in root.rglob(filename) if path.is_file())
    if len(matches) != 1:
        raise PersistenceError(
            f"expected exactly one retained source file {filename!r} under {root}; found {len(matches)}"
        )
    return matches[0]


def verify_corporate_action_sources(root: Path) -> dict:
    manifest_path = root / CORPORATE_MANIFEST
    merged_path = root / CORPORATE_MERGED
    if not manifest_path.is_file() or not merged_path.is_file():
        raise PersistenceError("corporate-action source directory is incomplete")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("contract") != "nse-corporate-actions-source-v1":
        raise PersistenceError("unexpected corporate-action source manifest contract")
    if sha256_file(merged_path) != manifest.get("merged_sha256"):
        raise PersistenceError("corporate-action merged payload hash mismatch")
    source_count = 0
    for row in manifest.get("sources") or []:
        source_count += 1
        if row.get("status") != "DOWNLOADED":
            raise PersistenceError(
                f"corporate-action source is not downloaded: {row.get('source_url')}"
            )
        source_file = row.get("source_file")
        if not source_file:
            raise PersistenceError(
                f"corporate-action source bytes were not retained: {row.get('source_url')}"
            )
        path = _find_unique(root, str(source_file))
        if sha256_file(path) != row.get("sha256"):
            raise PersistenceError(f"corporate-action source hash mismatch: {path}")
    if source_count == 0:
        raise PersistenceError("corporate-action source manifest has no sources")
    return {
        "source_count": source_count,
        "merged_row_count": int(manifest.get("merged_row_count") or 0),
        "manifest_sha256": sha256_file(manifest_path),
        "merged_sha256": sha256_file(merged_path),
    }


def verify_suspension_sources(root: Path) -> dict:
    manifest_path = root / SUSPENSION_MANIFEST
    if not manifest_path.is_file():
        raise PersistenceError("suspension source manifest is missing")
    rows = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise PersistenceError("suspension source manifest must be a non-empty list")
    pdf_sources = 0
    for row in rows:
        status = str(row.get("download_status") or "")
        if status != "DOWNLOADED":
            raise PersistenceError(
                f"suspension source is not downloaded: {row.get('source_url')} status={status}"
            )
        source_file = row.get("source_file_id")
        if not source_file:
            raise PersistenceError(
                f"suspension source bytes were not retained: {row.get('source_url')}"
            )
        path = _find_unique(root, str(source_file))
        if sha256_file(path) != row.get("sha256"):
            raise PersistenceError(f"suspension source hash mismatch: {path}")
        if row.get("media_type") == "application/pdf":
            pdf_sources += 1
    return {
        "source_count": len(rows),
        "pdf_source_count": pdf_sources,
        "manifest_sha256": sha256_file(manifest_path),
    }


def _stable_tar_gz(root: Path, output: Path, prefix: str) -> dict:
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files:
        raise PersistenceError(f"cannot archive empty directory: {root}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w") as tar:
                for path in files:
                    relative = path.relative_to(root).as_posix()
                    info = tar.gettarinfo(
                        str(path), arcname=f"{prefix}/{relative}"
                    )
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    info.mtime = 0
                    with path.open("rb") as handle:
                        tar.addfile(info, handle)
    return {
        "asset_name": output.name,
        "sha256": sha256_file(output),
        "bytes": output.stat().st_size,
        "file_count": len(files),
    }


def _copy_gate_file(source: Path, target: Path) -> dict:
    if not source.is_file():
        raise PersistenceError(f"required gate evidence is missing: {source}")
    shutil.copy2(source, target)
    return {
        "asset_name": target.name,
        "sha256": sha256_file(target),
        "bytes": target.stat().st_size,
    }


def _release_files(release_dir: Path) -> dict[str, dict[str, object]]:
    files = sorted(path for path in release_dir.iterdir() if path.is_file())
    if not files:
        raise PersistenceError("rebuilt release directory is empty")
    duplicate_names = {path.name for path in files if sum(p.name == path.name for p in files) > 1}
    if duplicate_names:
        raise PersistenceError(f"duplicate release asset names: {sorted(duplicate_names)}")
    return {
        path.name: {
            "asset_name": path.name,
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        for path in files
    }


def build_bundle(
    *,
    corporate_actions_dir: Path,
    suspensions_dir: Path,
    release_dir: Path,
    invariant: Path,
    candidate_audit: Path,
    output_dir: Path,
) -> dict:
    corporate_summary = verify_corporate_action_sources(corporate_actions_dir)
    suspension_summary = verify_suspension_sources(suspensions_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    corporate_archive = _stable_tar_gz(
        corporate_actions_dir,
        output_dir / "corporate_action_raw_sources.tar.gz",
        "corporate_actions",
    )
    suspension_archive = _stable_tar_gz(
        suspensions_dir,
        output_dir / "suspension_raw_sources.tar.gz",
        "suspensions",
    )
    gate_files = {
        "research_invariant_validation.json": _copy_gate_file(
            invariant, output_dir / "research_invariant_validation.json"
        ),
        "candidate_promotion_audit.json": _copy_gate_file(
            candidate_audit, output_dir / "candidate_promotion_audit.json"
        ),
    }
    manifest = {
        "contract": CONTRACT,
        "source_archives": {
            "corporate_actions": corporate_archive,
            "suspensions": suspension_archive,
        },
        "source_summaries": {
            "corporate_actions": corporate_summary,
            "suspensions": suspension_summary,
        },
        "gate_files": gate_files,
        "rebuilt_release_files": _release_files(release_dir),
    }
    manifest["logical_content_sha256"] = logical_sha256(manifest)
    manifest_path = output_dir / "pit_rebuild_persistence_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def verify_asset_directory(manifest_path: Path, asset_dir: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("contract") != CONTRACT:
        raise PersistenceError("unexpected PIT persistence manifest contract")
    expected: dict[str, str] = {}
    for row in (manifest.get("source_archives") or {}).values():
        expected[str(row["asset_name"])] = str(row["sha256"])
    for row in (manifest.get("gate_files") or {}).values():
        expected[str(row["asset_name"])] = str(row["sha256"])
    for row in (manifest.get("rebuilt_release_files") or {}).values():
        expected[str(row["asset_name"])] = str(row["sha256"])
    expected[manifest_path.name] = sha256_file(manifest_path)

    missing: list[str] = []
    mismatched: list[str] = []
    for name, digest in sorted(expected.items()):
        path = asset_dir / name
        if not path.is_file():
            missing.append(name)
        elif sha256_file(path) != digest:
            mismatched.append(name)
    if missing or mismatched:
        raise PersistenceError(
            f"persistent release verification failed: missing={missing}, mismatched={mismatched}"
        )
    return {
        "verified_asset_count": len(expected),
        "logical_content_sha256": manifest["logical_content_sha256"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--corporate-actions-dir", required=True)
    build.add_argument("--suspensions-dir", required=True)
    build.add_argument("--release-dir", required=True)
    build.add_argument("--invariant", required=True)
    build.add_argument("--candidate-audit", required=True)
    build.add_argument("--output-dir", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--manifest", required=True)
    verify.add_argument("--asset-dir", required=True)
    args = parser.parse_args()

    if args.command == "build":
        result = build_bundle(
            corporate_actions_dir=Path(args.corporate_actions_dir),
            suspensions_dir=Path(args.suspensions_dir),
            release_dir=Path(args.release_dir),
            invariant=Path(args.invariant),
            candidate_audit=Path(args.candidate_audit),
            output_dir=Path(args.output_dir),
        )
    else:
        result = verify_asset_directory(Path(args.manifest), Path(args.asset_dir))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
