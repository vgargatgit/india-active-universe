#!/usr/bin/env python3
"""Collect official NSE corporate-action rows for a bounded date range."""

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
USER_AGENT = "india-active-universe/phase3-recovery"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def request_bytes(opener: urllib.request.OpenerDirector, url: str, *, referer: str | None = None) -> bytes:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.8",
    }
    if referer:
        headers["Referer"] = referer
    request = urllib.request.Request(url, headers=headers)
    with opener.open(request, timeout=60) as response:
        payload = response.read()
        if response.status != 200:
            raise RuntimeError(f"NSE returned HTTP {response.status}: {url}")
        return payload


def fetch_range(opener: urllib.request.OpenerDirector, start: date, end: date) -> tuple[list[dict], bytes, str]:
    query = urllib.parse.urlencode(
        {
            "index": "equities",
            "from_date": start.strftime("%d-%m-%Y"),
            "to_date": end.strftime("%d-%m-%Y"),
        }
    )
    url = f"{API_URL}?{query}"
    payload = request_bytes(opener, url, referer=LANDING_URL)
    try:
        rows = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"NSE corporate-action response is not JSON for {start}..{end}") from exc
    if not isinstance(rows, list):
        raise RuntimeError(f"NSE corporate-action response is not a list for {start}..{end}")
    if any(not isinstance(row, dict) for row in rows):
        raise RuntimeError(f"NSE corporate-action response contains a non-object row for {start}..{end}")
    return rows, payload, url


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2006-01-01")
    parser.add_argument("--end", default="2026-08-10")
    parser.add_argument("--out", default="data/raw/nse/corporate_actions/corporate_actions_2006_2026.json")
    parser.add_argument("--raw-dir", default="data/raw/nse/corporate_actions/responses")
    parser.add_argument("--manifest", default="data/raw/nse/corporate_actions/source_manifest.json")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    if start > end:
        raise SystemExit("--start must be on or before --end")

    raw_dir = Path(args.raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    landing = request_bytes(opener, LANDING_URL)
    if b"Corporate Actions" not in landing and b"corporate" not in landing.lower():
        raise SystemExit("official NSE corporate-actions landing page did not validate")

    rows_by_key: dict[str, dict] = {}
    manifest_rows: list[dict] = [
        {
            "source_url": LANDING_URL,
            "source_file_id": "landing.html",
            "sha256": sha256_bytes(landing),
            "download_status": "DOWNLOADED",
            "parser_version": "nse-corporate-actions-v1",
        }
    ]
    (raw_dir / "landing.html").write_bytes(landing)

    for year in range(start.year, end.year + 1):
        bounded_start = max(start, date(year, 1, 1))
        bounded_end = min(end, date(year, 12, 31))
        rows, payload, url = fetch_range(opener, bounded_start, bounded_end)
        target = raw_dir / f"{year}.json"
        target.write_bytes(payload)
        manifest_rows.append(
            {
                "source_url": url,
                "source_file_id": target.name,
                "sha256": sha256_bytes(payload),
                "download_status": "DOWNLOADED",
                "parser_version": "nse-corporate-actions-v1",
                "row_count": len(rows),
            }
        )
        for row in rows:
            key = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            rows_by_key[key] = row
        time.sleep(0.2)

    output_rows = [rows_by_key[key] for key in sorted(rows_by_key)]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output_rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = Path(args.manifest)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(manifest_rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"rows": len(output_rows), "years": end.year - start.year + 1, "output": str(out)}, sort_keys=True))


if __name__ == "__main__":
    main()
