from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import json
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path


LANDING_URL = "https://www.nseindia.com/companies-listing/corporate-filings-actions"
API_URL = "https://www.nseindia.com/api/corporates-corporateActions"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0 Safari/537.36 india-active-universe/0.1"
)
REQUIRED_FIELDS = ("symbol", "series", "subject")


class CorporateActionRecoveryError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _date_arg(value: date) -> str:
    return value.strftime("%d-%m-%Y")


def build_url(start: date, end: date) -> str:
    query = urllib.parse.urlencode(
        {
            "index": "equities",
            "from_date": _date_arg(start),
            "to_date": _date_arg(end),
        }
    )
    return f"{API_URL}?{query}"


def validate_payload(payload: object, *, source_url: str) -> list[dict]:
    if not isinstance(payload, list):
        raise CorporateActionRecoveryError(
            f"corporate-action response is not a JSON list: {source_url}"
        )
    rows: list[dict] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise CorporateActionRecoveryError(
                f"corporate-action row {index} is not an object: {source_url}"
            )
        missing = [name for name in REQUIRED_FIELDS if not str(item.get(name) or "").strip()]
        if missing:
            raise CorporateActionRecoveryError(
                f"corporate-action row {index} lacks required fields {missing}: {source_url}"
            )
        if not (item.get("exDate") or item.get("recDate")):
            raise CorporateActionRecoveryError(
                f"corporate-action row {index} has neither exDate nor recDate: {source_url}"
            )
        rows.append(item)
    return rows


def row_identity(row: dict) -> str:
    """Stable full-row identity; preserves source corrections rather than guessing keys."""
    return json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def merge_rows(chunks: list[list[dict]]) -> list[dict]:
    unique: dict[str, dict] = {}
    for rows in chunks:
        for row in rows:
            unique.setdefault(row_identity(row), row)
    return sorted(
        unique.values(),
        key=lambda row: (
            str(row.get("exDate") or row.get("recDate") or ""),
            str(row.get("symbol") or ""),
            str(row.get("series") or ""),
            str(row.get("subject") or ""),
            row_identity(row),
        ),
    )


def _opener() -> urllib.request.OpenerDirector:
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def _request(opener: urllib.request.OpenerDirector, url: str, *, accept: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": LANDING_URL,
            "Connection": "keep-alive",
        },
    )
    with opener.open(request, timeout=90) as response:
        body = response.read()
        status = getattr(response, "status", 200)
        content_type = response.headers.get("Content-Type", "")
    if status != 200 or not body:
        raise CorporateActionRecoveryError(f"HTTP {status} or empty body from {url}")
    if "json" in accept and "json" not in content_type.lower():
        raise CorporateActionRecoveryError(
            f"unexpected content type {content_type!r} from {url}"
        )
    return body


def fetch_year(
    opener: urllib.request.OpenerDirector,
    *,
    year: int,
    requested_start: date,
    requested_end: date,
    attempts: int = 4,
) -> tuple[list[dict], bytes, str]:
    start = max(requested_start, date(year, 1, 1))
    end = min(requested_end, date(year, 12, 31))
    url = build_url(start, end)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            body = _request(opener, url, accept="application/json,text/plain,*/*")
            payload = json.loads(body.decode("utf-8"))
            return validate_payload(payload, source_url=url), body, url
        except Exception as exc:  # network boundary intentionally retried
            last_error = exc
            if attempt == attempts:
                break
            time.sleep(min(8.0, 0.75 * (2 ** (attempt - 1))))
            # Refresh cookies after NSE expires/challenges the session.
            try:
                _request(opener, LANDING_URL, accept="text/html,application/xhtml+xml")
            except Exception:
                pass
    raise CorporateActionRecoveryError(
        f"failed to fetch corporate actions for {year}: {last_error}"
    )


def collect(
    *,
    start: date,
    end: date,
    raw_dir: Path,
    output: Path,
    manifest_path: Path,
) -> dict:
    if start > end:
        raise CorporateActionRecoveryError("start must be on or before end")
    raw_dir.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    opener = _opener()
    landing = _request(opener, LANDING_URL, accept="text/html,application/xhtml+xml")
    source_rows: list[dict] = [
        {
            "source_type": "NSE_CORPORATE_ACTION_LANDING",
            "source_url": LANDING_URL,
            "sha256": sha256(landing),
            "bytes": len(landing),
            "parser_version": "nse-corporate-actions-recovery-v1",
            "status": "DOWNLOADED",
        }
    ]
    chunks: list[list[dict]] = []
    for year in range(start.year, end.year + 1):
        rows, body, url = fetch_year(
            opener,
            year=year,
            requested_start=start,
            requested_end=end,
        )
        digest = sha256(body)
        target = raw_dir / f"corporate_actions_{year}_{digest[:16]}.json"
        if target.exists() and sha256(target.read_bytes()) != digest:
            raise CorporateActionRecoveryError(f"cached source hash changed: {target}")
        if not target.exists():
            target.write_bytes(body)
        chunks.append(rows)
        source_rows.append(
            {
                "source_type": "NSE_CORPORATE_ACTION_API",
                "source_url": url,
                "year": year,
                "source_file": target.name,
                "sha256": digest,
                "bytes": len(body),
                "row_count": len(rows),
                "parser_version": "nse-corporate-actions-recovery-v1",
                "status": "DOWNLOADED",
            }
        )
        time.sleep(0.15)

    merged = merge_rows(chunks)
    if not merged:
        raise CorporateActionRecoveryError("official corporate-action collection returned zero rows")
    output.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "contract": "nse-corporate-actions-source-v1",
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "merged_row_count": len(merged),
        "merged_sha256": sha256(output.read_bytes()),
        "sources": source_rows,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2006-01-01")
    parser.add_argument("--end", default="2026-08-10")
    parser.add_argument(
        "--raw-dir", default="data/raw/nse/corporate_actions/source"
    )
    parser.add_argument(
        "--output",
        default="data/raw/nse/corporate_actions/corporate_actions_2006_2026.json",
    )
    parser.add_argument(
        "--manifest",
        default="data/raw/nse/corporate_actions/source_manifest.json",
    )
    args = parser.parse_args()
    result = collect(
        start=date.fromisoformat(args.start),
        end=date.fromisoformat(args.end),
        raw_dir=Path(args.raw_dir),
        output=Path(args.output),
        manifest_path=Path(args.manifest),
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
