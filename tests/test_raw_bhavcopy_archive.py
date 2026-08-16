from __future__ import annotations

import io
import json
import zipfile
from datetime import date
from pathlib import Path

import pytest

from india_active_universe.raw_bhavcopy_archive import (
    FetchResult,
    acquire_range,
    build_year_manifest,
    validate_archive_bytes,
    verify_year_manifest,
)


def _archive(symbol: str = "ABC") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "cm.csv",
            "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,TOTTRDQTY,TOTTRDVAL,ISIN\n"
            f"{symbol},EQ,10,11,9,10.5,100,1050,INE000A01001\n",
        )
    return buffer.getvalue()


def test_validate_archive_rejects_html_and_accepts_market_zip() -> None:
    assert validate_archive_bytes(b"<html>blocked</html>")[0] is False
    assert validate_archive_bytes(_archive())[0] is True


def test_acquire_reuses_files_and_remembers_confirmed_missing_dates(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    calls: list[str] = []

    def fetch(url: str) -> FetchResult:
        calls.append(url)
        if "20260101" in url or "01JAN2026" in url:
            return FetchResult("VALID", _archive(), url=url)
        return FetchResult("NOT_FOUND", url=url, detail="HTTP_404")

    first = acquire_range(
        root=root,
        start=date(2026, 1, 1),
        end=date(2026, 1, 2),
        fetch=fetch,
    )
    assert first["downloaded"] == 1
    assert first["newly_missing"] == 1
    assert (root / "2026-01-01.zip").is_file()
    assert first["known_missing_dates"] == ["2026-01-02"]

    manifest_path = tmp_path / "manifest.json"
    build_year_manifest(
        root=root,
        year=2026,
        known_missing_dates=first["known_missing_dates"],
        output=manifest_path,
    )
    calls.clear()
    second = acquire_range(
        root=root,
        start=date(2026, 1, 1),
        end=date(2026, 1, 2),
        previous_manifest=manifest_path,
        fetch=fetch,
    )
    assert second["reused"] == 1
    assert second["known_missing_skips"] == 1
    assert second["downloaded"] == 0
    assert calls == []


def test_acquire_uses_second_official_url_when_first_is_missing(tmp_path: Path) -> None:
    calls: list[str] = []

    def fetch(url: str) -> FetchResult:
        calls.append(url)
        if len(calls) == 1:
            return FetchResult("NOT_FOUND", url=url, detail="HTTP_404")
        return FetchResult("VALID", _archive("XYZ"), url=url)

    result = acquire_range(
        root=tmp_path,
        start=date(2026, 1, 5),
        end=date(2026, 1, 5),
        fetch=fetch,
    )
    assert result["downloaded"] == 1
    assert len(calls) == 2


def test_transient_failure_is_not_persisted_as_known_missing(tmp_path: Path) -> None:
    def fetch(url: str) -> FetchResult:
        return FetchResult("TRANSIENT_FAILURE", url=url, detail="TIMEOUT")

    result = acquire_range(
        root=tmp_path,
        start=date(2026, 1, 5),
        end=date(2026, 1, 5),
        fetch=fetch,
    )
    assert result["transient_failures"] == 1
    assert result["known_missing_dates"] == []
    assert result["failures"][0]["date"] == "2026-01-05"


def test_existing_invalid_file_fails_closed_instead_of_overwriting(tmp_path: Path) -> None:
    target = tmp_path / "2026-01-05.zip"
    target.write_bytes(b"not a zip")
    with pytest.raises(ValueError, match="will not be overwritten"):
        acquire_range(
            root=tmp_path,
            start=date(2026, 1, 5),
            end=date(2026, 1, 5),
            fetch=lambda _url: FetchResult("VALID", _archive()),
        )


def test_year_manifest_verifies_hashes_and_rejects_tampering(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    root.mkdir()
    source = root / "2026-01-05.zip"
    source.write_bytes(_archive())
    manifest = tmp_path / "manifest.json"
    payload = build_year_manifest(
        root=root,
        year=2026,
        known_missing_dates=["2026-01-06"],
        output=manifest,
    )
    assert payload["file_count"] == 1
    assert verify_year_manifest(root=root, manifest_path=manifest) == {
        "status": "PASS",
        "year": 2026,
        "file_count": 1,
        "total_bytes": source.stat().st_size,
        "known_missing_count": 1,
    }

    source.write_bytes(_archive("TAMPERED"))
    with pytest.raises(ValueError, match="mismatch"):
        verify_year_manifest(root=root, manifest_path=manifest)


def test_year_manifest_rejects_cross_year_missing_date(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    root.mkdir()
    manifest = tmp_path / "manifest.json"
    build_year_manifest(root=root, year=2026, known_missing_dates=[], output=manifest)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["known_missing_dates"] = ["2025-12-31"]
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="cross-year"):
        verify_year_manifest(root=root, manifest_path=manifest)
