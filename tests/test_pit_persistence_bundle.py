from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "build_pit_persistence_bundle.py"
SPEC = importlib.util.spec_from_file_location("build_pit_persistence_bundle", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def write(path: Path, content: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return module.sha256_file(path)


def fixture_tree(tmp_path: Path):
    corporate = tmp_path / "corporate"
    source = corporate / "source"
    landing_hash = write(source / "landing.html", b"<html>landing</html>")
    year_hash = write(source / "corporate_actions_2020.json", b"[]")
    merged_hash = write(corporate / module.CORPORATE_MERGED, b"[]\n")
    (corporate / module.CORPORATE_MANIFEST).write_text(
        json.dumps(
            {
                "contract": "nse-corporate-actions-source-v1",
                "merged_row_count": 1,
                "merged_sha256": merged_hash,
                "sources": [
                    {
                        "source_url": "landing",
                        "source_file": "landing.html",
                        "sha256": landing_hash,
                        "status": "DOWNLOADED",
                    },
                    {
                        "source_url": "year",
                        "source_file": "corporate_actions_2020.json",
                        "sha256": year_hash,
                        "status": "DOWNLOADED",
                    },
                ],
            },
            sort_keys=True,
        )
        + "\n"
    )

    suspensions = tmp_path / "suspensions"
    archive_hash = write(suspensions / "suspension_archive.html", b"<html>archive</html>")
    pdf_hash = write(suspensions / "notice.pdf", b"%PDF-fake")
    (suspensions / module.SUSPENSION_MANIFEST).write_text(
        json.dumps(
            [
                {
                    "source_url": "archive",
                    "source_file_id": "suspension_archive.html",
                    "sha256": archive_hash,
                    "download_status": "DOWNLOADED",
                    "media_type": "text/html",
                },
                {
                    "source_url": "notice",
                    "source_file_id": "notice.pdf",
                    "sha256": pdf_hash,
                    "download_status": "DOWNLOADED",
                    "media_type": "application/pdf",
                },
            ],
            sort_keys=True,
        )
        + "\n"
    )

    release = tmp_path / "release"
    write(release / "security_master.parquet", b"security")
    write(release / "research_universe_monthly.parquet", b"monthly")
    invariant = tmp_path / "invariant.json"
    candidate = tmp_path / "candidate.json"
    write(invariant, b'{"status":"PASS"}\n')
    write(candidate, b'{"candidate":"PASS"}\n')
    return corporate, suspensions, release, invariant, candidate


def test_build_bundle_hashes_raw_sources_gates_and_every_release_file(tmp_path: Path) -> None:
    corporate, suspensions, release, invariant, candidate = fixture_tree(tmp_path)
    output = tmp_path / "out"

    manifest = module.build_bundle(
        corporate_actions_dir=corporate,
        suspensions_dir=suspensions,
        release_dir=release,
        invariant=invariant,
        candidate_audit=candidate,
        output_dir=output,
    )

    assert manifest["contract"] == module.CONTRACT
    assert manifest["source_summaries"]["corporate_actions"]["source_count"] == 2
    assert manifest["source_summaries"]["suspensions"]["source_count"] == 2
    assert manifest["source_summaries"]["suspensions"]["pdf_source_count"] == 1
    assert set(manifest["rebuilt_release_files"]) == {
        "security_master.parquet",
        "research_universe_monthly.parquet",
    }
    assert (output / "corporate_action_raw_sources.tar.gz").is_file()
    assert (output / "suspension_raw_sources.tar.gz").is_file()
    assert (output / "pit_rebuild_persistence_manifest.json").is_file()


def test_stable_archives_are_byte_identical(tmp_path: Path) -> None:
    corporate, suspensions, release, invariant, candidate = fixture_tree(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"
    module.build_bundle(
        corporate_actions_dir=corporate,
        suspensions_dir=suspensions,
        release_dir=release,
        invariant=invariant,
        candidate_audit=candidate,
        output_dir=first,
    )
    module.build_bundle(
        corporate_actions_dir=corporate,
        suspensions_dir=suspensions,
        release_dir=release,
        invariant=invariant,
        candidate_audit=candidate,
        output_dir=second,
    )
    assert (first / "corporate_action_raw_sources.tar.gz").read_bytes() == (
        second / "corporate_action_raw_sources.tar.gz"
    ).read_bytes()
    assert (first / "suspension_raw_sources.tar.gz").read_bytes() == (
        second / "suspension_raw_sources.tar.gz"
    ).read_bytes()


def test_verify_asset_directory_checks_every_persisted_asset(tmp_path: Path) -> None:
    corporate, suspensions, release, invariant, candidate = fixture_tree(tmp_path)
    output = tmp_path / "out"
    manifest = module.build_bundle(
        corporate_actions_dir=corporate,
        suspensions_dir=suspensions,
        release_dir=release,
        invariant=invariant,
        candidate_audit=candidate,
        output_dir=output,
    )
    assets = tmp_path / "assets"
    assets.mkdir()
    for row in manifest["source_archives"].values():
        (assets / row["asset_name"]).write_bytes((output / row["asset_name"]).read_bytes())
    for row in manifest["gate_files"].values():
        (assets / row["asset_name"]).write_bytes((output / row["asset_name"]).read_bytes())
    for name in manifest["rebuilt_release_files"]:
        (assets / name).write_bytes((release / name).read_bytes())
    manifest_path = output / "pit_rebuild_persistence_manifest.json"
    (assets / manifest_path.name).write_bytes(manifest_path.read_bytes())

    result = module.verify_asset_directory(manifest_path, assets)
    assert result["verified_asset_count"] == 7

    (assets / "security_master.parquet").write_bytes(b"changed")
    with pytest.raises(module.PersistenceError, match="mismatched"):
        module.verify_asset_directory(manifest_path, assets)


def test_missing_raw_source_bytes_fail_closed(tmp_path: Path) -> None:
    corporate, suspensions, release, invariant, candidate = fixture_tree(tmp_path)
    (corporate / "source" / "landing.html").unlink()
    with pytest.raises(module.PersistenceError, match="retained source file"):
        module.build_bundle(
            corporate_actions_dir=corporate,
            suspensions_dir=suspensions,
            release_dir=release,
            invariant=invariant,
            candidate_audit=candidate,
            output_dir=tmp_path / "out",
        )


def test_failed_suspension_source_blocks_persistence(tmp_path: Path) -> None:
    corporate, suspensions, release, invariant, candidate = fixture_tree(tmp_path)
    rows = json.loads((suspensions / module.SUSPENSION_MANIFEST).read_text())
    rows[1]["download_status"] = "FAILED:OSError"
    (suspensions / module.SUSPENSION_MANIFEST).write_text(json.dumps(rows) + "\n")
    with pytest.raises(module.PersistenceError, match="not downloaded"):
        module.build_bundle(
            corporate_actions_dir=corporate,
            suspensions_dir=suspensions,
            release_dir=release,
            invariant=invariant,
            candidate_audit=candidate,
            output_dir=tmp_path / "out",
        )
