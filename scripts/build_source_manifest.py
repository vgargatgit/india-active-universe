from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from india_active_universe.nse import candidate_urls


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="data/raw/nse/bhavcopy")
    parser.add_argument("--out", default="data/raw/manifests/source_manifest.json")
    args = parser.parse_args()

    output = []
    for path in sorted(Path(args.root).glob("*.zip")):
        source_date = path.stem
        point = datetime.strptime(source_date, "%Y-%m-%d").date()
        with zipfile.ZipFile(path) as archive:
            members = [name for name in archive.namelist() if name.lower().endswith((".csv", ".txt"))]
        output.append({
            "source_file_id": path.name,
            "source_url": candidate_urls(point)[0] if point.year < 2024 else candidate_urls(point)[1],
            "local_path": str(path),
            "source_date": source_date,
            "retrieved_at_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
            "retrieval_timestamp_basis": "LOCAL_FILE_MTIME",
            "sha256": sha256(path),
            "parser_version": "nse-bhavcopy-v2",
            "download_status": "DOWNLOADED_VALID_ARCHIVE",
            "content_type": "application/zip",
            "http_etag": None,
            "archive_members": members,
        })
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"files": len(output), "first_date": output[0]["source_date"] if output else None, "last_date": output[-1]["source_date"] if output else None}, sort_keys=True))


if __name__ == "__main__":
    main()
