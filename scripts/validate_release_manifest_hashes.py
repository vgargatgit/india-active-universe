#!/usr/bin/env python3
"""Validate published release artifact hashes against manifest metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_manifest_hashes(release: Path) -> list[str]:
    manifest_path = release / "data_release_manifest.json"
    if not manifest_path.is_file():
        return [f"missing manifest: {manifest_path.name}"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    if manifest.get("release_id") and manifest["release_id"] != release.name:
        failures.append(f"release_id mismatch: {manifest['release_id']} != {release.name}")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        failures.append("manifest artifacts must be a non-empty object")
        return failures
    for key, expected in sorted(artifacts.items()):
        if not isinstance(expected, str) or len(expected) != 64:
            failures.append(f"invalid sha256 field: {key}")
            continue
        relative = key.removeprefix("release/")
        artifact = release / relative
        if not artifact.is_file():
            failures.append(f"missing artifact: {key}")
        elif sha256(artifact) != expected:
            failures.append(f"hash mismatch: {key}")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    args = parser.parse_args()
    failures = validate_manifest_hashes(Path(args.release))
    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        raise SystemExit(1)
    print("MANIFEST_HASHES_VALID")


if __name__ == "__main__":
    main()
