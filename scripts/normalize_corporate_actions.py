from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from india_active_universe.storage import read_jsonl, write_jsonl


def parse_date(value: str | None) -> str | None:
    if not value or value == "-":
        return None
    return datetime.strptime(value, "%d-%b-%Y").date().isoformat()


def classify(subject: str) -> str:
    text = subject.upper()
    if "BONUS" in text:
        return "BONUS"
    if "SPLIT" in text or "SUB-DIVISION" in text:
        return "SPLIT"
    if "CONSOLID" in text:
        return "REVERSE_SPLIT"
    if "RIGHT" in text:
        return "RIGHTS"
    if "DEMERGER" in text:
        return "DEMERGER"
    if "MERGER" in text or "AMALGAM" in text:
        return "MERGER"
    if "SCHEME" in text:
        return "SCHEME"
    if "BUYBACK" in text or "BUY BACK" in text:
        return "BUYBACK"
    if "DIV" in text:
        return "DIVIDEND"
    if "NAME" in text:
        return "NAME_CHANGE"
    return "OTHER_OFFICIAL_ACTION"


def ratio(subject: str) -> tuple[int | None, int | None, str | None]:
    match = re.search(r"(\d+)\s*:\s*(\d+)", subject)
    if not match:
        return None, None, None
    return int(match.group(1)), int(match.group(2)), match.group(0)


def face_value_transition(subject: str, event_type: str) -> tuple[float | None, float | None, float | None]:
    """Return old face value, new face value, and price factor when unambiguous."""
    if event_type not in {"SPLIT", "REVERSE_SPLIT"}:
        return None, None, None
    values = [float(value) for value in re.findall(r"(?:RS\.?|RE\s+)(\d+(?:\.\d+)?)", subject.upper())]
    if len(values) != 2 or values[0] <= 0 or values[1] <= 0:
        return None, None, None
    return values[0], values[1], values[1] / values[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default="data/raw/nse/corporate_actions/corporate_actions_2006_2026.json")
    parser.add_argument("--master", default="data/canonical/security_master.jsonl")
    parser.add_argument("--out", default="data/canonical/corporate_actions.jsonl")
    args = parser.parse_args()
    raw = json.loads(Path(args.raw).read_text(encoding="utf-8"))
    master = read_jsonl(args.master)
    isin_to_security = {row["isin"]: row["security_id"] for row in master if row.get("isin") and row.get("series") == "EQ"}
    output = []
    for index, item in enumerate(raw):
        if item.get("series") != "EQ":
            continue
        subject = (item.get("subject") or "").strip()
        event_type = classify(subject)
        numerator, denominator, ratio_raw = ratio(subject)
        old_face_value, new_face_value, face_price_factor = face_value_transition(subject, event_type)
        event_date = parse_date(item.get("exDate")) or parse_date(item.get("recDate"))
        if not event_date:
            continue
        price_factor = None
        share_factor = None
        if event_type == "BONUS" and numerator is not None and denominator:
            share_factor = (numerator + denominator) / denominator
            price_factor = 1.0 / share_factor
        if event_type in {"SPLIT", "REVERSE_SPLIT"} and face_price_factor is not None:
            price_factor = face_price_factor
            share_factor = 1.0 / face_price_factor
        output.append({"event_id": f"NSE_CA_{index:06d}", "security_id": isin_to_security.get(item.get("isin")), "issuer_id": None, "exchange": "NSE", "symbol_at_event": item.get("symbol"), "isin": item.get("isin"), "series": item.get("series"), "event_type": event_type, "event_date": event_date, "ex_date": parse_date(item.get("exDate")), "record_date": parse_date(item.get("recDate")), "subject": subject, "face_value": item.get("faceVal"), "old_face_value": old_face_value, "new_face_value": new_face_value, "ratio_raw": ratio_raw, "ratio_numerator": numerator, "ratio_denominator": denominator, "price_factor": price_factor, "share_factor": share_factor, "source": "NSE_OFFICIAL_CORPORATE_ACTION_FEED", "source_file_id": Path(args.raw).name, "source_quality": "OFFICIAL_EXCHANGE_ACTION_FEED", "review_status": "RESOLVED_BY_ISIN" if item.get("isin") in isin_to_security else "IDENTITY_REVIEW_REQUIRED", "notes": None})
    write_jsonl(args.out, output, overwrite=True)
    print(json.dumps({"events": len(output), "linked_security_ids": sum(row["security_id"] is not None for row in output), "unresolved_identity": sum(row["security_id"] is None for row in output)}, sort_keys=True))


if __name__ == "__main__":
    main()
