from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_release_manifest_hashes import sha256, validate_manifest_hashes


def write_manifest(release: Path, digest: str) -> None:
    (release / "data_release_manifest.json").write_text(
        json.dumps(
            {
                "release_id": release.name,
                "artifacts": {
                    "release/sample.parquet": digest,
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def test_manifest_hash_validator_accepts_matching_artifact(tmp_path: Path):
    release = tmp_path / "india_equity_data_test"
    release.mkdir()
    artifact = release / "sample.parquet"
    artifact.write_bytes(b"parquet bytes")
    write_manifest(release, sha256(artifact))
    assert validate_manifest_hashes(release) == []


def test_manifest_hash_validator_rejects_modified_artifact(tmp_path: Path):
    release = tmp_path / "india_equity_data_test"
    release.mkdir()
    artifact = release / "sample.parquet"
    artifact.write_bytes(b"parquet bytes")
    write_manifest(release, sha256(artifact))
    artifact.write_bytes(b"changed bytes")
    assert validate_manifest_hashes(release) == ["hash mismatch: release/sample.parquet"]
