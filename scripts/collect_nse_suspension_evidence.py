from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from pypdf import PdfReader


ARCHIVE_URL = "https://www.nseindia.com/static/resources/exchange-communication-press-releases-archives"
PARSER_VERSION = "nse-suspension-v2"
_PRESS_LINK_RE = re.compile(
    r"href=[\"']([^\"']*/content/press/(\d{2})(\d{2})(\d{4})\.(htm|pdf)(?:\?[^\"']*)?)[\"']",
    re.I,
)
_EVENT_INDEX_RE = re.compile(
    r"suspension|suspended|revocation|recommencement|available\s+for\s+trading",
    re.I,
)
_EVENT_BODY_RE = re.compile(
    r"suspension|suspended|revocation|recommencement|available\s+for\s+trading",
    re.I,
)


@dataclass(frozen=True)
class FetchedDocument:
    content: bytes
    media_type: str
    resolved_url: str


class TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = html.unescape(re.sub(r"\s+", " ", data)).strip()
        if value:
            self.parts.append(value)


def _request_once(url: str) -> FetchedDocument:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 india-active-universe/0.1",
            "Accept": "text/html,application/xhtml+xml,application/pdf",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        content = response.read()
        content_type = response.headers.get("Content-Type", "")
        resolved_url = response.geturl()
    if not content:
        raise ValueError(f"empty source document: {url}")
    if content.startswith(b"%PDF-") or "pdf" in content_type.lower():
        if not content.startswith(b"%PDF-"):
            raise ValueError(f"source claims PDF but has no PDF signature: {url}")
        return FetchedDocument(content, "application/pdf", resolved_url)
    if b"<html" in content[:8192].lower():
        return FetchedDocument(content, "text/html", resolved_url)
    raise ValueError(
        f"source is neither HTML nor PDF: {url}; content_type={content_type!r}"
    )


def alternate_nse_url(url: str) -> str | None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.netloc == "nsearchives.nseindia.com":
        host = "www.nseindia.com"
    elif parsed.netloc in {"www.nseindia.com", "nseindia.com"}:
        host = "nsearchives.nseindia.com"
    else:
        return None
    return urllib.parse.urlunsplit(
        (parsed.scheme or "https", host, parsed.path, parsed.query, parsed.fragment)
    )


def fetch(url: str, *, attempts: int = 4) -> FetchedDocument:
    failures: list[str] = []
    candidates = [url]
    alternate = alternate_nse_url(url)
    if alternate and alternate != url:
        candidates.append(alternate)
    for candidate in candidates:
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return _request_once(candidate)
            except Exception as exc:
                last_error = exc
                if attempt < attempts:
                    time.sleep(min(8.0, 0.75 * (2 ** (attempt - 1))))
        assert last_error is not None
        failures.append(f"{candidate}: {type(last_error).__name__}: {last_error}")
    raise OSError("; ".join(failures))


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def source_failure_count(rows: list[dict[str, object]]) -> int:
    return sum(
        str(row.get("download_status") or "").startswith("FAILED:")
        for row in rows
    )


def failed_sources(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        row
        for row in rows
        if str(row.get("download_status") or "").startswith("FAILED:")
    ]


def _strip_html(value: str) -> str:
    value = re.sub(r"<script\b.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def archive_candidates(
    archive_url: str,
    archive_content: bytes,
    *,
    start: str,
    end: str,
) -> list[dict[str, str]]:
    """Select only official daily releases whose archive summary signals status evidence.

    The NSE archive is the discovery authority. Fetching every daily press page is both
    unnecessarily brittle and semantically noisy: many pages merely mention companies
    that were already suspended in complaint tables. A date is selected only when the
    archive's own summary contains a suspension/revocation/recommencement/trading-
    availability signal. Both legacy HTML and PDF press documents are supported.
    """

    decoded = archive_content.decode("utf-8", errors="replace")
    matches = list(_PRESS_LINK_RE.finditer(decoded))
    selected: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, match in enumerate(matches):
        href, dd, mm, yyyy, extension = match.groups()
        publication_date = f"{yyyy}-{mm}-{dd}"
        if not start <= publication_date <= end:
            continue
        segment_end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else min(len(decoded), match.end() + 8000)
        )
        archive_context = _strip_html(decoded[match.start():segment_end])
        if not _EVENT_INDEX_RE.search(archive_context):
            continue
        source_url = urllib.parse.urljoin(archive_url, href)
        if source_url in seen:
            continue
        seen.add(source_url)
        selected.append(
            {
                "source_url": source_url,
                "publication_date": publication_date,
                "document_type": extension.lower(),
                "archive_context": archive_context[:2000],
            }
        )
    return selected


def document_text(document: FetchedDocument) -> str:
    if document.media_type == "text/html":
        parser = TextParser()
        parser.feed(document.content.decode("utf-8", errors="replace"))
        return "\n".join(parser.parts)
    if document.media_type == "application/pdf":
        reader = PdfReader(io.BytesIO(document.content))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
        text = "\n".join(page for page in pages if page)
        if not text.strip():
            raise ValueError("official NSE PDF contains no extractable text")
        return text
    raise ValueError(f"unsupported source media type: {document.media_type}")


def article_date(text: str) -> str | None:
    match = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b",
        text,
        re.I,
    )
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
    return (
        datetime.strptime(value.group(0).title(), "%B %d, %Y").date().isoformat()
        if value
        else None
    )


def event_type(text: str) -> str:
    lowered = text.lower()
    if (
        "revocation" in lowered
        or "recommencement" in lowered
        or "available for trading" in lowered
    ):
        return "SUSPENSION_REVOKED"
    return "SUSPENSION_START"


def candidate_names(text: str) -> list[str]:
    names = []
    for match in _EVENT_BODY_RE.finditer(text):
        window = text[max(0, match.start() - 120) : match.start() + 1000]
        for candidate in re.findall(
            r"\b[A-Z][A-Za-z0-9&.'’()/-]*(?:\s+[A-Z][A-Za-z0-9&.'’()/-]*){0,8}\s+(?:Limited|Ltd\.?)\b",
            window,
        ):
            clean = re.sub(r"\s+", " ", candidate).strip(" .,-")
            upper = clean.upper()
            if any(
                term in upper
                for term in (
                    "NATIONAL STOCK EXCHANGE",
                    "PRESS RELEASE",
                    "CAPITAL MARKET",
                    "LISTING AGREEMENT",
                    "TRADING IN",
                    "SECURITIES OF",
                )
            ):
                continue
            if 3 <= len(clean) <= 140:
                names.append(clean)
    return list(dict.fromkeys(names))[:100]


def _source_extension(media_type: str) -> str:
    return ".pdf" if media_type == "application/pdf" else ".html"


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
        help="Exploratory-only escape hatch: preserve partial results even when selected official event pages fail to download.",
    )
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    archive_document = fetch(args.archive_url)
    if archive_document.media_type != "text/html":
        raise SystemExit("official NSE press archive index is not HTML")
    archive = archive_document.content
    selected = archive_candidates(
        args.archive_url,
        archive,
        start=args.start,
        end=args.end,
    )
    if not selected:
        raise SystemExit("official NSE archive yielded no suspension-related source documents")

    rows: list[dict[str, object]] = []
    source_rows: list[dict[str, object]] = [
        {
            "source_url": args.archive_url,
            "resolved_source_url": archive_document.resolved_url,
            "source_file_id": "suspension_archive.html",
            "sha256": sha256(archive),
            "download_status": "DOWNLOADED",
            "media_type": "text/html",
            "parser_version": PARSER_VERSION,
        }
    ]
    cached_sources: dict[str, Path] = {}
    source_manifest_path = raw_dir / "source_manifest.json"
    if source_manifest_path.exists():
        for cached in json.loads(source_manifest_path.read_text(encoding="utf-8")):
            if cached.get("source_url") and cached.get("source_file_id"):
                cached_sources[str(cached["source_url"])] = raw_dir / str(
                    cached["source_file_id"]
                )

    for index, item in enumerate(selected):
        try:
            cached_path = cached_sources.get(item["source_url"])
            if cached_path and cached_path.exists():
                cached_content = cached_path.read_bytes()
                media_type = (
                    "application/pdf"
                    if cached_content.startswith(b"%PDF-")
                    else "text/html"
                )
                document = FetchedDocument(
                    cached_content,
                    media_type,
                    item["source_url"],
                )
            else:
                document = fetch(item["source_url"])
            digest = sha256(document.content)
            target = raw_dir / f"{digest}{_source_extension(document.media_type)}"
            if target.exists() and sha256(target.read_bytes()) != digest:
                raise IOError(f"raw source changed: {target}")
            if not target.exists():
                target.write_bytes(document.content)
            source_rows.append(
                {
                    "source_url": item["source_url"],
                    "resolved_source_url": document.resolved_url,
                    "source_file_id": target.name,
                    "sha256": digest,
                    "download_status": "DOWNLOADED",
                    "media_type": document.media_type,
                    "archive_context": item["archive_context"],
                    "parser_version": PARSER_VERSION,
                }
            )
            text = document_text(document)
            published = article_date(text) or item["publication_date"]
            if not _EVENT_BODY_RE.search(text):
                raise ValueError(
                    "archive classified source as suspension-related but document text contains no status signal"
                )
            rows.append(
                {
                    "evidence_id": f"NSE_SUSP_{index:06d}",
                    "source_file_id": target.name,
                    "source_url": item["source_url"],
                    "published_date": published,
                    "event_type": event_type(text),
                    "effective_date": effective_date(text),
                    "historical_company_names": candidate_names(text),
                    "identity_quality": "IDENTITY_REVIEW_REQUIRED",
                    "source_quality": "NSE_OFFICIAL_PRESS_ARCHIVE",
                    "text_excerpt": text[:1200],
                }
            )
            time.sleep(0.05)
        except Exception as exc:
            source_rows.append(
                {
                    "source_url": item["source_url"],
                    "resolved_source_url": None,
                    "source_file_id": None,
                    "sha256": None,
                    "download_status": f"FAILED:{type(exc).__name__}",
                    "error": str(exc),
                    "archive_context": item["archive_context"],
                    "parser_version": PARSER_VERSION,
                }
            )

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    schema = pa.schema(
        [
            pa.field("evidence_id", pa.string()),
            pa.field("source_file_id", pa.string()),
            pa.field("source_url", pa.string()),
            pa.field("published_date", pa.string()),
            pa.field("event_type", pa.string()),
            pa.field("effective_date", pa.string()),
            pa.field("historical_company_names", pa.list_(pa.string())),
            pa.field("identity_quality", pa.string()),
            pa.field("source_quality", pa.string()),
            pa.field("text_excerpt", pa.string()),
        ]
    )
    pq.write_table(
        pa.Table.from_pylist(rows, schema=schema),
        output,
        compression="zstd",
        use_dictionary=True,
    )
    source_manifest_path.write_text(
        json.dumps(source_rows, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    failures = source_failure_count(source_rows)
    expected_sources = len(selected) + 1
    if len(source_rows) != expected_sources:
        raise SystemExit(
            f"suspension source manifest is not exhaustive: expected {expected_sources} rows, got {len(source_rows)}"
        )
    failure_rows = failed_sources(source_rows)
    print(
        json.dumps(
            {
                "archive_event_links": len(selected),
                "evidence_rows": len(rows),
                "raw_source_rows": len(source_rows),
                "source_failures": failures,
                "failed_sources": failure_rows,
            },
            sort_keys=True,
        )
    )
    if failures and not args.allow_source_errors:
        raise SystemExit(
            f"official suspension source acquisition has {failures} failed event documents; see {source_manifest_path}"
        )


if __name__ == "__main__":
    main()
