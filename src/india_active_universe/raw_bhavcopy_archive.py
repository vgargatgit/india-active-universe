from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable

from .nse import candidate_urls

SCHEMA_VERSION = 1
SOURCE_TYPE = "NSE_OFFICIAL_CASH_EQUITY_BHAVCOPY"
USER_AGENT = "Mozilla/5.0"
REFERER = "https://www.nseindia.com/"


@dataclass(frozen=True)
class FetchResult:
    status: str
    content: bytes | None = None
    url: str | None = None
    detail: str | None = None


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_archive_bytes(content: bytes) -> tuple[bool, str]:
    if not content:
        return False, "EMPTY_FILE"
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = [name for name in archive.namelist() if name.lower().endswith((".csv", ".txt"))]
            if not members:
                return False, "NO_CSV_MEMBER"
            header = archive.open(members[0]).readline().decode("utf-8-sig", errors="replace")
    except (OSError, zipfile.BadZipFile, UnicodeError):
        return False, "INVALID_ZIP_ARCHIVE"
    fields = {field.strip().upper().replace(" ", "_") for field in next(csv.reader(io.StringIO(header)), [])}
    if not ({"SYMBOL", "SERIES"} <= fields or {"TCKRSYMB", "SCTYSRS"} <= fields):
        return False, "MISSING_REQUIRED_MARKET_COLUMNS"
    return True, "VALID_NSE_MARKET_ARCHIVE"


def validate_archive_file(path: str | Path) -> tuple[bool, str]:
    source = Path(path)
    if not source.is_file():
        return False, "MISSING_FILE"
    return validate_archive_bytes(source.read_bytes())


def iter_weekdays(start: date, end: date) -> Iterable[date]:
    point = start
    while point <= end:
        if point.weekday() < 5:
            yield point
        point += timedelta(days=1)


def _http_fetch(url: str, timeout: float = 45.0) -> FetchResult:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Referer": REFERER})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return FetchResult("NOT_FOUND", url=url, detail=f"HTTP_{exc.code}")
        return FetchResult("TRANSIENT_FAILURE", url=url, detail=f"HTTP_{exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return FetchResult("TRANSIENT_FAILURE", url=url, detail=type(exc).__name__)
    valid, detail = validate_archive_bytes(content)
    if not valid:
        return FetchResult("INVALID_PAYLOAD", url=url, detail=detail)
    return FetchResult("VALID", content=content, url=url, detail=detail)


def _load_known_missing(previous_manifest: str | Path | None) -> set[str]:
    if not previous_manifest:
        return set()
    path = Path(previous_manifest)
    if not path.is_file():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported previous bhavcopy manifest schema")
    values = payload.get("known_missing_dates", [])
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        raise ValueError("known_missing_dates must be a list of ISO dates")
    return set(values)


def _fetch_candidates(point: date, fetch: Callable[[str], FetchResult]) -> list[FetchResult]:
    results: list[FetchResult] = []
    for url in candidate_urls(point):
        result = fetch(url)
        results.append(result)
        if result.status == "VALID":
            break
    return results


def acquire_range(
    *,
    root: str | Path,
    start: date,
    end: date,
    previous_manifest: str | Path | None = None,
    fetch: Callable[[str], FetchResult] = _http_fetch,
) -> dict:
    if end < start:
        raise ValueError("end must be on or after start")
    root_path = Path(root)
    root_path.mkdir(parents=True, exist_ok=True)
    known_missing = _load_known_missing(previous_manifest)
    reused = downloaded = known_missing_skips = newly_missing = transient_failures = 0
    failures: list[dict] = []

    for point in iter_weekdays(start, end):
        iso = point.isoformat()
        target = root_path / f"{iso}.zip"
        if target.exists():
            valid, detail = validate_archive_file(target)
            if not valid:
                raise ValueError(f"existing cached bhavcopy is invalid and will not be overwritten: {target}: {detail}")
            reused += 1
            continue
        if iso in known_missing:
            known_missing_skips += 1
            continue

        results = _fetch_candidates(point, fetch)
        valid_result = next((result for result in results if result.status == "VALID"), None)
        if valid_result is not None and valid_result.content is not None:
            with tempfile.NamedTemporaryFile(dir=root_path, prefix=f".{iso}.", suffix=".part", delete=False) as handle:
                part = Path(handle.name)
                handle.write(valid_result.content)
            try:
                valid, detail = validate_archive_file(part)
                if not valid:
                    raise ValueError(f"downloaded bhavcopy failed validation: {iso}: {detail}")
                part.replace(target)
            finally:
                part.unlink(missing_ok=True)
            downloaded += 1
            continue

        statuses = {result.status for result in results}
        if len(results) == len(candidate_urls(point)) and statuses == {"NOT_FOUND"}:
            known_missing.add(iso)
            newly_missing += 1
            continue
        transient_failures += 1
        failures.append(
            {
                "date": iso,
                "attempts": [
                    {"url": result.url, "status": result.status, "detail": result.detail}
                    for result in results
                ],
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "source_type": SOURCE_TYPE,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "reused": reused,
        "downloaded": downloaded,
        "known_missing_skips": known_missing_skips,
        "newly_missing": newly_missing,
        "transient_failures": transient_failures,
        "known_missing_dates": sorted(known_missing),
        "failures": failures,
    }


def build_year_manifest(
    *,
    root: str | Path,
    year: int,
    known_missing_dates: Iterable[str],
    output: str | Path,
) -> dict:
    root_path = Path(root)
    files = []
    total_bytes = 0
    for path in sorted(root_path.glob(f"{year:04d}-*.zip")):
        valid, detail = validate_archive_file(path)
        if not valid:
            raise ValueError(f"cannot manifest invalid bhavcopy {path.name}: {detail}")
        size = path.stat().st_size
        files.append(
            {
                "source_date": path.stem,
                "path": path.name,
                "bytes": size,
                "sha256": sha256_file(path),
            }
        )
        total_bytes += size
    missing = sorted({value for value in known_missing_dates if value.startswith(f"{year:04d}-")})
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "source_type": SOURCE_TYPE,
        "year": year,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "file_count": len(files),
        "total_bytes": total_bytes,
        "known_missing_dates": missing,
        "files": files,
    }
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def verify_year_manifest(*, root: str | Path, manifest_path: str | Path) -> dict:
    root_path = Path(root)
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("source_type") != SOURCE_TYPE:
        raise ValueError("unsupported bhavcopy year manifest")
    year = int(manifest["year"])
    expected = manifest.get("files")
    if not isinstance(expected, list):
        raise ValueError("manifest files must be a list")
    expected_names: set[str] = set()
    total_bytes = 0
    for row in expected:
        name = row.get("path")
        if not isinstance(name, str) or Path(name).name != name or not name.startswith(f"{year:04d}-") or not name.endswith(".zip"):
            raise ValueError(f"unsafe or cross-year bhavcopy path: {name!r}")
        if name in expected_names:
            raise ValueError(f"duplicate bhavcopy path: {name}")
        expected_names.add(name)
        path = root_path / name
        if not path.is_file():
            raise ValueError(f"manifested bhavcopy missing: {name}")
        if path.stat().st_size != row.get("bytes"):
            raise ValueError(f"bhavcopy size mismatch: {name}")
        if sha256_file(path) != row.get("sha256"):
            raise ValueError(f"bhavcopy sha256 mismatch: {name}")
        valid, detail = validate_archive_file(path)
        if not valid:
            raise ValueError(f"manifested bhavcopy is invalid: {name}: {detail}")
        total_bytes += path.stat().st_size
    actual_names = {path.name for path in root_path.glob(f"{year:04d}-*.zip")}
    extras = sorted(actual_names - expected_names)
    if extras:
        raise ValueError(f"unmanifested bhavcopy files: {extras[:10]}")
    if manifest.get("file_count") != len(expected_names):
        raise ValueError("manifest file_count mismatch")
    if manifest.get("total_bytes") != total_bytes:
        raise ValueError("manifest total_bytes mismatch")
    missing = manifest.get("known_missing_dates", [])
    if not isinstance(missing, list) or any(not value.startswith(f"{year:04d}-") for value in missing):
        raise ValueError("known_missing_dates contains a cross-year value")
    return {
        "status": "PASS",
        "year": year,
        "file_count": len(expected_names),
        "total_bytes": total_bytes,
        "known_missing_count": len(missing),
    }


def _date(value: str) -> date:
    return date.fromisoformat(value)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m india_active_universe.raw_bhavcopy_archive")
    sub = parser.add_subparsers(dest="command", required=True)

    acquire = sub.add_parser("acquire")
    acquire.add_argument("--root", required=True)
    acquire.add_argument("--start", required=True)
    acquire.add_argument("--end", required=True)
    acquire.add_argument("--previous-manifest")
    acquire.add_argument("--output", required=True)

    build = sub.add_parser("build-manifest")
    build.add_argument("--root", required=True)
    build.add_argument("--year", required=True, type=int)
    build.add_argument("--state", required=True)
    build.add_argument("--output", required=True)

    verify = sub.add_parser("verify")
    verify.add_argument("--root", required=True)
    verify.add_argument("--manifest", required=True)

    args = parser.parse_args()
    if args.command == "acquire":
        result = acquire_range(
            root=args.root,
            start=_date(args.start),
            end=_date(args.end),
            previous_manifest=args.previous_manifest,
        )
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    elif args.command == "build-manifest":
        state = json.loads(Path(args.state).read_text(encoding="utf-8"))
        result = build_year_manifest(
            root=args.root,
            year=args.year,
            known_missing_dates=state.get("known_missing_dates", []),
            output=args.output,
        )
    else:
        result = verify_year_manifest(root=args.root, manifest_path=args.manifest)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
