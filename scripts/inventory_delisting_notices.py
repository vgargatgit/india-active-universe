from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from pypdf import PdfReader


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relevance(text: str, filename: str) -> tuple[str, list[str]]:
    """Classify notice evidence without promoting uncertain documents."""
    compact = re.sub(r"\s+", " ", text).strip()
    lowered = compact.lower()
    terms = []
    for term in (
        "compulsory delisting",
        "public notice for compulsory delisting",
        "delisting committee",
        "delisting regulations",
        "national stock exchange of india",
    ):
        if term in lowered:
            terms.append(term.upper())
    if not compact:
        return "SCANNED_DOCUMENT_REVIEW_REQUIRED", terms
    if "compulsory delist" in lowered and "national stock exchange" in lowered:
        return "RELEVANT_TEXT_EVIDENCE", terms
    if "delist" in lowered and "national stock exchange" in lowered:
        return "POSSIBLE_TEXT_EVIDENCE_REVIEW_REQUIRED", terms
    if "e-auction" in lowered or "business standard" in lowered:
        return "NOT_RELEVANT_TEXT", terms
    return "NOT_RELEVANT_TEXT", terms


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="data/raw/nse/notices/compulsory_delisting")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    output = []
    for path in sorted(Path(args.root).glob("*.pdf")):
        try:
            reader = PdfReader(path)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            status = "TEXT_EXTRACTED" if text.strip() else "SCANNED_DOCUMENT_OCR_REQUIRED"
            pages = len(reader.pages)
        except Exception as exc:
            status, pages, text = f"PARSE_FAILURE:{type(exc).__name__}", None, ""
        match = re.search(r"(\d{8})", path.name)
        relevance_status, evidence_terms = relevance(text, path.name)
        compact = re.sub(r"\s+", " ", text).strip()
        output.append({"source_file_id": path.name, "source_sha256": sha256(path), "notice_date": f"{match.group(1)[4:]}-{match.group(1)[2:4]}-{match.group(1)[:2]}" if match else None, "document_type": "FINAL" if "FINAL" in path.name.upper() else "INITIAL", "language": "ENGLISH", "page_count": pages, "text_character_count": len(text), "parse_status": status, "relevance_status": relevance_status, "evidence_terms": evidence_terms, "text_excerpt": compact[:1000] if compact else None, "source": "NSE_OFFICIAL_NOTICE_URL"})
    schema = pa.schema([pa.field("source_file_id", pa.string()), pa.field("source_sha256", pa.string()), pa.field("notice_date", pa.string()), pa.field("document_type", pa.string()), pa.field("language", pa.string()), pa.field("page_count", pa.int64()), pa.field("text_character_count", pa.int64()), pa.field("parse_status", pa.string()), pa.field("relevance_status", pa.string()), pa.field("evidence_terms", pa.list_(pa.string())), pa.field("text_excerpt", pa.string()), pa.field("source", pa.string())])
    pq.write_table(pa.Table.from_pylist(output, schema=schema), args.out, compression="zstd", use_dictionary=True)
    print(json.dumps({"documents": len(output), "text_extracted": sum(row["parse_status"] == "TEXT_EXTRACTED" for row in output), "ocr_required": sum(row["parse_status"] == "SCANNED_DOCUMENT_OCR_REQUIRED" for row in output), "relevant_text": sum(row["relevance_status"] == "RELEVANT_TEXT_EVIDENCE" for row in output), "not_relevant_text": sum(row["relevance_status"] == "NOT_RELEVANT_TEXT" for row in output)}, sort_keys=True))


if __name__ == "__main__":
    main()
