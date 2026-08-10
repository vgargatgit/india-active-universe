from __future__ import annotations

import hashlib
from pathlib import Path

from .provenance import SourceManifestEntry, manifest_entry, write_manifest


class ImmutableRawStore:
    """Content-addressed raw storage. Existing source-date artifacts are never replaced."""

    def __init__(self, root: str | Path = "data/raw") -> None:
        self.root = Path(root)
        self.manifest_path = self.root / "manifests" / "source_manifest.json"
        self.entries: list[SourceManifestEntry] = []

    def put(self, *, source_url: str, source_date: str | None, content: bytes, filename: str, parser_version: str, content_type: str | None = None) -> Path:
        digest = hashlib.sha256(content).hexdigest()
        target = self.root / "nse" / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.read_bytes() != content:
                raise FileExistsError(f"Refusing to overwrite changed raw artifact: {target}")
        else:
            target.write_bytes(content)
        entry = manifest_entry(Path(filename).stem, source_url, target, source_date, parser_version, content_type=content_type)
        if not any(item.source_file_id == entry.source_file_id for item in self.entries):
            self.entries.append(entry)
            write_manifest(self.manifest_path, self.entries)
        if entry.sha256 != digest:
            raise IOError("Raw artifact checksum changed during write")
        return target
