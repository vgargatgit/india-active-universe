#!/usr/bin/env python3
"""Promote a verified release into a new immutable cached release."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from india_active_universe.profiles import (
    CACHED_PROMOTION_BUILD_MODE,
    REQUIRED_RELEASE_ARTIFACTS,
    SOURCE_MANIFEST_ARTIFACT,
    SUSPENSION_SOURCE_MANIFEST_ARTIFACT,
    TARGET_RELEASE_ID,
)

REQUIRED = tuple(name for name in REQUIRED_RELEASE_ARTIFACTS if name.endswith(".parquet"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit(root: Path) -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def verify_parent(source: Path, manifest: dict) -> None:
    missing = [name for name in REQUIRED if not (source / name).is_file()]
    if missing:
        raise SystemExit("Parent release is missing required artifacts: " + ", ".join(missing))
    mismatches = []
    for key, expected in manifest.get("artifacts", {}).items():
        if not key.startswith("release/"):
            continue
        path = source / key.removeprefix("release/")
        if path.is_file() and sha256(path) != expected:
            mismatches.append(key)
    if mismatches:
        raise SystemExit("Parent release hash mismatch: " + ", ".join(mismatches))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--source-release", required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    source = (root / args.source_release).resolve()
    target = (root / "releases" / args.release_id).resolve()
    if args.release_id == TARGET_RELEASE_ID:
        raise SystemExit(f"{TARGET_RELEASE_ID} must be built from source with build_source_release.py, not cached promotion")
    manifest_path = source / "data_release_manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"Parent release manifest does not exist: {manifest_path}")
    if target.exists():
        raise SystemExit(f"Immutable target already exists: {target}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    verify_parent(source, manifest)
    if args.dry_run:
        print(json.dumps({"source": str(source), "target": str(target), "artifacts": len(REQUIRED), "mode": CACHED_PROMOTION_BUILD_MODE}, sort_keys=True))
        return

    staging = target.parent / f".{target.name}.tmp"
    if staging.exists():
        raise SystemExit(f"Staging directory already exists: {staging}")
    staging.mkdir(parents=True)
    try:
        for path in sorted(source.iterdir()):
            if path.is_file() and (path.suffix == ".parquet" or path.name in {SOURCE_MANIFEST_ARTIFACT, SUSPENSION_SOURCE_MANIFEST_ARTIFACT}):
                shutil.copy2(path, staging / path.name)
        output_manifest = dict(manifest)
        output_manifest["release_id"] = args.release_id
        output_manifest["parent_release_id"] = manifest.get("release_id")
        output_manifest["source_release_id"] = manifest.get("release_id")
        output_manifest["source_release_manifest_sha256"] = sha256(manifest_path)
        output_manifest["git_commit"] = git_commit(root)
        output_manifest["build_mode"] = CACHED_PROMOTION_BUILD_MODE
        output_manifest["manifest_note"] = "Cached promotion. Parent artifact hashes were verified before copy."
        output_manifest["artifacts"] = {f"release/{name}": sha256(staging / name) for name in sorted(p.name for p in staging.iterdir() if p.is_file())}
        (staging / "data_release_manifest.json").write_text(json.dumps(output_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        staging.rename(target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(json.dumps({"release_id": args.release_id, "parent_release_id": manifest.get("release_id"), "artifacts": len(output_manifest["artifacts"]), "mode": CACHED_PROMOTION_BUILD_MODE}, sort_keys=True))


if __name__ == "__main__":
    main()
