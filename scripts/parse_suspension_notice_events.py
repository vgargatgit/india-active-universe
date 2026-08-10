from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from collect_nse_suspension_evidence import TextParser, effective_date


def clean(value: object) -> str:
    value = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
    return value.replace("LIMITED", "LTD").replace("CORPORATION", "CORP")


def event_type(text: str) -> str:
    lowered = text.lower()
    if "recommencement" in lowered or "available for trading" in lowered:
        return "TRADING_RECOMMENCEMENT"
    if "revocation" in lowered:
        return "SUSPENSION_REVOKED"
    return "SUSPENSION_START"


def is_status_action(text: str) -> bool:
    lowered = text.lower()
    return bool(
        re.search(r"revocation\s+of\s+(?:the\s+)?suspension|recommencement\s+of\s+trading", lowered)
        or re.search(r"(?:will|shall|would|are|be)\s+suspended\s+from\s+trading", lowered)
        or "proposed suspension" in lowered
    )


def publication_date(value: str | None) -> str | None:
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", required=True)
    parser.add_argument("--raw-dir", required=True)
    parser.add_argument("--master", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    master = pq.read_table(args.master).to_pylist()
    names: dict[str, list[dict]] = defaultdict(list)
    for row in master:
        name = clean(row.get("company_name"))
        if len(name) >= 8:
            names[name].append(row)

    output = []
    for page in pq.read_table(args.pages).to_pylist():
        path = Path(args.raw_dir) / page["source_file_id"]
        text_parser = TextParser()
        text_parser.feed(path.read_text(encoding="utf-8", errors="replace"))
        text = "\n".join(text_parser.parts)
        blocks = re.split(r"(?i)press\s+release\s+no\.\s*\d+", text)
        block_number = 0
        for block in blocks:
            if not is_status_action(block):
                continue
            block_number += 1
            focus = block[:1400]
            normalized_focus = clean(focus)
            candidates = []
            for name, rows in names.items():
                if name in normalized_focus:
                    candidates.extend(rows)
            point = effective_date(block) or publication_date(page.get("published_date"))
            dated = [row for row in candidates if point and row["first_seen"] <= point <= row["last_seen"]]
            unique = {row["security_id"]: row for row in dated}
            if len(unique) == 1:
                candidate = next(iter(unique.values()))
                quality = "EXACT_NAME_BLOCK_DATE_MATCH"
                security_id = candidate["security_id"]
                issuer_id = candidate.get("issuer_id")
                episode_id = candidate.get("listing_episode_id")
                historical_name = candidate.get("company_name")
            else:
                quality = "EVENT_LEVEL_IDENTITY_REVIEW_REQUIRED"
                security_id = issuer_id = episode_id = historical_name = None
            output.append({"evidence_id": f"{page['evidence_id']}_BLOCK_{block_number:02d}", "page_evidence_id": page["evidence_id"], "source_file_id": page["source_file_id"], "source_url": page["source_url"], "published_date": page.get("published_date"), "event_type": event_type(block), "effective_date": effective_date(block), "historical_company_name": historical_name, "security_id": security_id, "issuer_id": issuer_id, "listing_episode_id": episode_id, "identity_match_quality": quality, "source_quality": "NSE_OFFICIAL_PRESS_ARCHIVE", "text_excerpt": re.sub(r"\s+", " ", block).strip()[:1600]})

    schema = pa.schema([pa.field("evidence_id", pa.string()), pa.field("page_evidence_id", pa.string()), pa.field("source_file_id", pa.string()), pa.field("source_url", pa.string()), pa.field("published_date", pa.string()), pa.field("event_type", pa.string()), pa.field("effective_date", pa.string()), pa.field("historical_company_name", pa.string()), pa.field("security_id", pa.string()), pa.field("issuer_id", pa.string()), pa.field("listing_episode_id", pa.string()), pa.field("identity_match_quality", pa.string()), pa.field("source_quality", pa.string()), pa.field("text_excerpt", pa.string())])
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(output, schema=schema), target, compression="zstd", use_dictionary=True)
    print({"page_count": pq.read_metadata(args.pages).num_rows, "event_blocks": len(output), "exact_matches": sum(row["identity_match_quality"] == "EXACT_NAME_BLOCK_DATE_MATCH" for row in output)})


if __name__ == "__main__":
    main()
