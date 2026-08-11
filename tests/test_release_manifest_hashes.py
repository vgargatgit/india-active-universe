from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq

from scripts.publish_parquet import publish
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


def test_publish_preserves_list_valued_unresolved_candidates(tmp_path: Path):
    source = tmp_path / "unresolved_observed_trading.jsonl"
    target = tmp_path / "unresolved_observed_trading.parquet"
    source.write_text(
        json.dumps(
            {
                "date": "2020-01-01",
                "symbol": "ABC",
                "candidate_security_ids": ["SEC1", "SEC2"],
            }
        ) + "\n",
        encoding="utf-8",
    )

    assert publish(source, target) == 1

    row = pq.read_table(target).to_pylist()[0]
    assert row["candidate_security_ids"] == ["SEC1", "SEC2"]
