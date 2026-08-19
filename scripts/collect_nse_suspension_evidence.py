from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


ARCHIVE_URL = "https://www.nseindia.com/static/resources/exchange-communication-press-releases-archives"


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            self.links.append({"href": self._href, "title": re.sub(r"\s+", " ", " ".join(self._text)).strip()})
            self._href = None
            self._text = []


class TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = html.unescape(re.sub(r"\s+", " ", data)).strip()
        if value:
            self.parts.append(value)


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "india-active-universe/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        content = response.read()
        content_type = response.headers.get("Content-Type", "")
    if not content or b"<html" not in content[:4096].lower() or "html" not in content_type.lower():
        raise ValueError(f"source is not an HTML document: {url}")
    return content


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def source_failure_count(rows: list[dict[str, object]]) -> int:
    return sum(
        str(row.get("download_status") or "").startswith("FAILED:")
        for row in rows
    )


def article_date(text: str) -> str | None:
    match = re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b", text, re.I)
    if not match:
        return None
    return datetime.strptime(match.group(0).title(), "%B %d, %Y").date().isoformat()


def effective_date(text: str) -> str | None:
    date_pattern = r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}"
    marker_pattern = r"(?:w\s*\.\s*e\s*\.\s*f\s*\.?|effective(?:ly)?\s+from|with\s+effect\s+from)"
    match = re.search(rf"{marker_pattern}\s+(?:the\s+)?{date_pattern}", text, re.I)
    if not match:
        return None
    value = re.search(date_pattern, match.group(0), re.I)
    return datetime.strptime(value.group(0).title(), "%B %d, %Y").date().isoformat() if value else None


def event_type(text: str) -> str:
    lowered = text.lower()
    if "revocation" in lowered or "recommencement" in lowered or "available for trading" in lowered:
        return "SUSPENSION_REVOKED"
    return "SUSPENSION_START"


def candidate_names(text: str) -> list[str]:
    names = []
    for match in re.finditer(r"suspension|suspended|revocation|recommencement", text, re.I):
        window = text[max(0, match.start() - 120):match.start() + 1000]
        for candidate in re.findall(r"\b[A-Z][A-Za-z0-9&.'’()/-]*(?:\s+[A-Z][A-Za-z0-9&.'’()/-]*){0,8}\s+(?:Limited|Ltd\.?)\b", window):
            clean = re.sub(r"\s+", " ", candidate).strip(" .,-")
            upper = clean.upper()
            if any(term in upper for term in ("NATIONAL STOCK EXCHANGE", "PRESS RELEASE", "CAPITAL MARKET", "LISTING AGREEMENT", "TRADING IN", "SECURITIES OF")):
                continue
            if 3 <= len(clean) <= 140:
                names.append(clean)
    return list(dict.fromkeys(names))[:100]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-url", default=ARCHIVE_URL)
    parser.add_argument("--raw-dir", default="data/raw/nse/notices/suspensions")
    parser.add_argument("--out", required=True)
    parser.add_argument("--start", default="2006-01-01")
    parser.add_argument("--end", default="2026-08-10")
    parser.add_argument(
        "--allow-source-errors",
        action="store_true",
        help="Exploratory-only escape hatch: preserve partial results even when selected official pages fail to download.",
    )
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    archive = fetch(args.archive_url)
    links = LinkParser()
    links.feed(archive.decode("utf-8", errors="replace"))
    selected = []
    for link in links.links:
        title = link["title"]
        url = urllib.parse.urljoin(args.archive_url, link["href"])
        if "/content/press/" not in url:
            continue
        date_match = re.search(r"/(\d{2})(\d{2})(\d{4})\.htm(?:$|\?)", url)
        if not date_match:
            continue
        publication_date = f"{date_match.group(3)}-{date_match.group(2)}-{date_match.group(1)}"
        if not args.start <= publication_date <= args.end:
            continue
        if url not in {item["source_url"] for item in selected}:
            selected.append({"source_url": url, "title": title, "publication_date": publication_date})

    rows = []
    source_rows = [{"source_url": args.archive_url, "source_file_id": "suspension_archive.html", "sha256": sha256(archive), "download_status": "DOWNLOADED", "parser_version": "nse-suspension-v1"}]
    cached_sources = {}
    source_manifest_path = raw_dir / "source_manifest.json"
    if source_manifest_path.exists():
        for cached in json.loads(source_manifest_path.read_text(encoding="utf-8")):
            if cached.get("source_url") and cached.get("source_file_id"):
                cached_sources[cached["source_url"]] = raw_dir / cached["source_file_id"]
    for index, item in enumerate(selected):
        try:
            cached_path = cached_sources.get(item["source_url"])
            content = cached_path.read_bytes() if cached_path and cached_path.exists() else fetch(item["source_url"])
            digest = sha256(content)
            target = raw_dir / f"{digest}.html"
            if target.exists() and sha256(target.read_bytes()) != digest:
                raise IOError(f"raw source changed: {target}")
            if not target.exists():
                target.write_bytes(content)
            parser_text = TextParser()
            parser_text.feed(content.decode("utf-8", errors="replace"))
            text = "\n".join(parser_text.parts)
            published = article_date(text)
            if not re.search(r"suspension|suspended|revocation|recommencement", text, re.I):
                continue
            rows.append({"evidence_id": f"NSE_SUSP_{index:06d}", "source_file_id": target.name, "source_url": item["source_url"], "published_date": published, "event_type": event_type(text), "effective_date": effective_date(text), "historical_company_names": candidate_names(text), "identity_quality": "IDENTITY_REVIEW_REQUIRED", "source_quality": "NSE_OFFICIAL_PRESS_ARCHIVE", "text_excerpt": text[:1200]})
            source_rows.append({"source_url": item["source_url"], "source_file_id": target.name, "sha256": digest, "download_status": "DOWNLOADED", "parser_version": "nse-suspension-v1"})
            time.sleep(0.05)
        except Exception as exc:
            source_rows.append({"source_url": item["source_url"], "source_file_id": None, "sha256": None, "download_status": f"FAILED:{type(exc).__name__}", "parser_version": "nse-suspension-v1"})

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    schema = pa.schema([pa.field("evidence_id", pa.string()), pa.field("source_file_id", pa.string()), pa.field("source_url", pa.string()), pa.field("published_date", pa.string()), pa.field("event_type", pa.string()), pa.field("effective_date", pa.string()), pa.field("historical_company_names", pa.list_(pa.string())), pa.field("identity_quality", pa.string()), pa.field("source_quality", pa.string()), pa.field("text_excerpt", pa.string())])
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), output, compression="zstd", use_dictionary=True)
    source_manifest_path.write_text(json.dumps(source_rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    failures = source_failure_count(source_rows)
    print(json.dumps({"archive_links": len(selected), "evidence_rows": len(rows), "raw_source_rows": len(source_rows), "source_failures": failures}, sort_keys=True))
    if failures and not args.allow_source_errors:
        raise SystemExit(
            f"official suspension source acquisition has {failures} failed pages; see {source_manifest_path}"
        )


if __name__ == "__main__":
    main()
