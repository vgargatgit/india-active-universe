from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class SourceManifestEntry:
    source_file_id: str
    source_url: str
    local_path: str
    source_date: str | None
    retrieved_at_utc: str
    sha256: str
    parser_version: str
    download_status: str
    content_type: str | None = None
    http_etag: str | None = None


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_entry(source_file_id: str, url: str, path: str | Path, source_date: str | None, parser_version: str, *, status: str = "DOWNLOADED", content_type: str | None = None) -> SourceManifestEntry:
    local = Path(path)
    return SourceManifestEntry(source_file_id, url, str(local), source_date, datetime.now(timezone.utc).isoformat(), sha256_file(local), parser_version, status, content_type)


def write_manifest(path: str | Path, entries: list[SourceManifestEntry]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps([asdict(entry) for entry in entries], indent=2, sort_keys=True) + "\n", encoding="utf-8")
