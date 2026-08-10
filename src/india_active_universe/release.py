from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def hash_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_release_manifest(path: str | Path, *, release_id: str, git_commit: str, coverage: dict[str, Any], artifacts: dict[str, str], quality: dict[str, Any]) -> None:
    manifest = {"release_id": release_id, "project_id": "india-active-universe", "git_commit": git_commit, "coverage": coverage, "artifacts": artifacts, "quality": quality}
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
