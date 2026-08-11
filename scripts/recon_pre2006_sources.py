#!/usr/bin/env python3
"""Probe representative pre-2006 official NSE bhavcopy archives."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from india_active_universe.nse import candidate_urls
from validate_nse_archive import validate

PARSER_VERSION = "nse-pre2006-recon-v1"
DEFAULT_DATES = ("2004-01-30", "2004-12-31", "2005-01-31", "2005-12-30")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_header(path: Path) -> tuple[list[str], str | None]:
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith((".csv", ".txt"))]
        if not members:
            return [], None
        raw = archive.read(members[0]).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    fields = [field.strip().upper().replace(" ", "_") for field in (reader.fieldnames or []) if field]
    return fields, members[0]


def schema_profile(path: Path) -> dict:
    fields, member = normalized_header(path)
    symbol_key = "SYMBOL" if "SYMBOL" in fields else "TCKRSYMB" if "TCKRSYMB" in fields else None
    series_key = "SERIES" if "SERIES" in fields else "SCTYSRS" if "SCTYSRS" in fields else None
    traded_value_keys = {"NET_TURNOV", "TOTTRDVAL", "TOTAL_TRADED_VALUE", "TTLTRFVAL"}
    profile = {
        "archive_member": member,
        "columns": fields,
        "has_eq_series": False,
        "has_isin": "ISIN" in fields,
        "has_traded_value": bool(traded_value_keys & set(fields)),
        "eq_rows": 0,
        "total_rows": 0,
    }
    if not member or not symbol_key or not series_key:
        return profile
    with zipfile.ZipFile(path) as archive:
        raw = archive.read(member).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    for original in reader:
        row = {key.strip().upper().replace(" ", "_"): value for key, value in original.items() if key}
        profile["total_rows"] += 1
        if (row.get(series_key) or "").strip().upper() == "EQ":
            profile["eq_rows"] += 1
    profile["has_eq_series"] = profile["eq_rows"] > 0
    return profile


def fetch(url: str, timeout: int) -> tuple[bytes | None, dict]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.nseindia.com/",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content = response.read()
            return content, {
                "http_status": getattr(response, "status", None),
                "content_type": response.headers.get("Content-Type"),
                "http_etag": response.headers.get("ETag"),
                "content_length": response.headers.get("Content-Length"),
            }
    except urllib.error.HTTPError as exc:
        return None, {"http_status": exc.code, "content_type": exc.headers.get("Content-Type"), "error": f"HTTPError:{exc.code}"}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, {"http_status": None, "content_type": None, "error": type(exc).__name__}


def probe_date(point: date, raw_dir: Path, *, timeout: int, offline: bool) -> dict:
    target = raw_dir / f"{point.isoformat()}.zip"
    base = {
        "source_date": point.isoformat(),
        "source_file_id": target.name,
        "local_path": str(target),
        "parser_version": PARSER_VERSION,
        "retrieved_at_utc": None,
        "retrieval_timestamp_basis": None,
        "download_status": None,
        "source_url": None,
        "candidate_urls": candidate_urls(point),
        "sha256": None,
        "content_type": None,
        "http_etag": None,
    }
    if target.exists():
        valid, message = validate(target)
        base.update({
            "download_status": "CACHED_VALID_ARCHIVE" if valid else f"CACHED_INVALID:{message}",
            "sha256": sha256_file(target) if target.is_file() else None,
            "retrieved_at_utc": datetime.fromtimestamp(target.stat().st_mtime, timezone.utc).isoformat() if target.is_file() else None,
            "retrieval_timestamp_basis": "LOCAL_FILE_MTIME",
        })
        if valid:
            base.update(schema_profile(target))
        return base
    if offline:
        base["download_status"] = "NOT_CACHED_OFFLINE"
        return base
    raw_dir.mkdir(parents=True, exist_ok=True)
    for url in candidate_urls(point):
        content, metadata = fetch(url, timeout)
        if content is None:
            base.update({"source_url": url, "download_status": metadata.get("error") or "DOWNLOAD_FAILED", **metadata})
            continue
        digest = sha256_bytes(content)
        with NamedTemporaryFile(delete=False, dir=raw_dir, suffix=".part") as handle:
            handle.write(content)
            part = Path(handle.name)
        valid, message = validate(part)
        if valid:
            part.replace(target)
            base.update({
                "source_url": url,
                "download_status": "DOWNLOADED_VALID_ARCHIVE",
                "sha256": digest,
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "retrieval_timestamp_basis": "HTTP_RETRIEVAL_TIME",
                **metadata,
            })
            base.update(schema_profile(target))
            return base
        part.unlink(missing_ok=True)
        base.update({"source_url": url, "download_status": f"DOWNLOADED_INVALID:{message}", "sha256": digest, **metadata})
    return base


def report(rows: list[dict]) -> str:
    lines = [
        "# Pre-2006 NSE source reconnaissance",
        "",
        "This report probes representative official NSE cash-market bhavcopy archive dates before 2006.",
        "It is reconnaissance only; it does not promote an early research interval.",
        "",
        "| Source date | Status | URL pattern | EQ rows | ISIN | Traded value | Archive member | Notes |",
        "|---|---|---|---:|---|---|---|---|",
    ]
    for row in rows:
        url = row.get("source_url") or ""
        pattern = "legacy" if "/historical/EQUITIES/" in url else "udiff" if "BhavCopy_NSE_CM" in url else "none"
        notes = []
        if row.get("download_status") not in {"DOWNLOADED_VALID_ARCHIVE", "CACHED_VALID_ARCHIVE"}:
            notes.append(str(row.get("error") or row.get("download_status")))
        if row.get("columns") and not row.get("has_isin"):
            notes.append("ISIN column absent")
        if row.get("columns") and not row.get("has_traded_value"):
            notes.append("traded-value column absent")
        lines.append(
            f"| {row['source_date']} | `{row.get('download_status')}` | `{pattern}` | "
            f"{row.get('eq_rows', '')} | {'Y' if row.get('has_isin') else 'N'} | "
            f"{'Y' if row.get('has_traded_value') else 'N'} | `{row.get('archive_member') or ''}` | "
            f"{'; '.join(notes)} |"
        )
    valid_count = sum(1 for row in rows if row.get("download_status") in {"DOWNLOADED_VALID_ARCHIVE", "CACHED_VALID_ARCHIVE"})
    lines.extend([
        "",
        f"Valid representative archives: `{valid_count}` of `{len(rows)}`.",
        "",
        "Corporate-action source compatibility is not established by daily bhavcopy reconnaissance.",
        "If representative market archives pass, corporate-action source compatibility must be checked separately before early-period promotion.",
        "",
        "No current-survivor list is used here.",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dates", nargs="*", default=list(DEFAULT_DATES))
    parser.add_argument("--raw-dir", default="data/raw/nse/bhavcopy_pre2006_recon")
    parser.add_argument("--manifest", default="data/raw/manifests/pre2006_source_reconnaissance.json")
    parser.add_argument("--report", default="reports/pre2006_source_reconnaissance.md")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--offline", action="store_true", help="Only inspect cached representative archives; do not download.")
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)
    rows = [probe_date(date.fromisoformat(value), raw_dir, timeout=args.timeout, offline=args.offline) for value in args.dates]
    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report(rows), encoding="utf-8")
    print(json.dumps({"dates": len(rows), "valid_archives": sum(1 for row in rows if row.get("download_status") in {"DOWNLOADED_VALID_ARCHIVE", "CACHED_VALID_ARCHIVE"}), "report": str(report_path)}, sort_keys=True))


if __name__ == "__main__":
    main()
