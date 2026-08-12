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
    has_bonus = "BONUS" in text or re.search(r"\bBON\s*\d+\s*:\s*\d+", text) is not None
    if has_bonus and ("PREFERENCE" in text or "NCRPS" in text):
        return "BONUS_PREFERENCE_SECURITY"
    if has_bonus and "DEBENTURE" not in text:
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
        match = re.search(r"BONUS\s+(\d+)\s+(?:DVR\s+)?[^:]*:\s*(\d+)", subject.upper())
    if not match:
        return None, None, None
    return int(match.group(1)), int(match.group(2)), match.group(0)


def face_value_transition(subject: str, event_type: str) -> tuple[float | None, float | None, float | None]:
    """Return old face value, new face value, and price factor when unambiguous."""
    if event_type not in {"SPLIT", "REVERSE_SPLIT", "BONUS"}:
        return None, None, None
    text = subject.upper()
    transition = re.search(
        r"FROM(?:\s+FACE\s+VALUE)?\s*(?:R[SE]\.?)?\s*(\d+(?:\.\d+)?)\s*/?-?\D+"
        r"TO(?:\s+FACE\s+VALUE)?\s*(?:R[SE]\.?)?\s*(\d+(?:\.\d+)?)",
        text,
    )
    if not transition:
        transition = re.search(r"CONSOLIDATION.*?R[SE]\.?\s*(\d+(?:\.\d+)?)\D+TO\s+R[SE]\.?\s*(\d+(?:\.\d+)?)", text)
    if not transition:
        transition = re.search(r"SPL(?:IT)?\s*[-:/ ]+\s*R[SE]\.?\s*(\d+(?:\.\d+)?)\s*/?\s*TO\s*(\d+(?:\.\d+)?)\s*/?", text)
    if not transition:
        transition = re.search(r"FV\s+SPL\s*[-:/ ]+\s*(\d+(?:\.\d+)?)\s*/?\s*TO\s*(\d+(?:\.\d+)?)\s*/?", text)
    values = [float(value) for value in transition.groups()] if transition else [float(value) for value in re.findall(r"R[SE]\.?\s*(\d+(?:\.\d+)?)", text)]
    if len(values) != 2 or values[0] <= 0 or values[1] <= 0:
        return None, None, None
    return values[0], values[1], values[1] / values[0]


def dividend_amount(subject: str, face_value: object, event_type: str) -> tuple[float | None, str | None]:
    if event_type != "DIVIDEND":
        return None, None
    amounts = [float(value) for value in re.findall(r"RS\.?\s*(\d+(?:\.\d+)?)", subject.upper())]
    if amounts:
        return sum(amounts), "OFFICIAL_SUBJECT_RUPEE_AMOUNT"
    percentages = [float(value) for value in re.findall(r"(\d+(?:\.\d+)?)\s*%", subject.upper())]
    try:
        face = float(face_value)
    except (TypeError, ValueError):
        face = None
    if percentages and face is not None and face > 0:
        return face * sum(percentages) / 100.0, "OFFICIAL_FACE_VALUE_PERCENT"
    return None, None


def has_unsupported_rights_component(subject: str, event_type: str) -> bool:
    """Return true when a material price action also contains unsupported rights terms."""
    return event_type in {"BONUS", "SPLIT", "REVERSE_SPLIT"} and "RIGHT" in subject.upper()


def load_resolutions(path: str | None) -> dict[str, dict]:
    if not path:
        return {}
    resolution_path = Path(path)
    if not resolution_path.is_file():
        return {}
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - environment dependency
        raise SystemExit("PyYAML is required for corporate action resolutions") from exc
    payload = yaml.safe_load(resolution_path.read_text(encoding="utf-8")) or {}
    rows = payload.get("resolutions") or []
    if not isinstance(rows, list):
        raise SystemExit("corporate action resolutions must contain a resolutions list")
    resolutions = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise SystemExit(f"corporate action resolution[{index}] must be a mapping")
        event_id = row.get("event_id")
        if not event_id:
            raise SystemExit(f"corporate action resolution[{index}] missing event_id")
        if row.get("review_status") != "APPROVED":
            raise SystemExit(f"corporate action resolution[{index}] is not APPROVED")
        evidence = row.get("evidence_references")
        if not isinstance(evidence, list) or not evidence:
            raise SystemExit(f"corporate action resolution[{index}] needs evidence_references")
        if not str(row.get("rationale") or "").strip():
            raise SystemExit(f"corporate action resolution[{index}] needs rationale")
        resolutions[str(event_id)] = row
    return resolutions


def composite_rights_price_factor(cum_price: float, bonus_ratio: float, rights_ratio: float, subscription_price: float) -> float:
    if cum_price <= 0:
        raise ValueError("cum_price must be positive")
    post_shares = 1.0 + bonus_ratio + rights_ratio
    return (cum_price + rights_ratio * subscription_price) / post_shares / cum_price


def selective_bonus_price_factor(pre_total_shares: float, post_total_shares: float) -> float:
    if pre_total_shares <= 0 or post_total_shares <= 0:
        raise ValueError("share counts must be positive")
    return pre_total_shares / post_total_shares


def apply_resolution(row: dict, resolution: dict | None) -> dict:
    if not resolution:
        return row
    row = dict(row)
    if resolution.get("resolved_event_type"):
        row["event_type"] = resolution["resolved_event_type"]
    if resolution.get("resolved_price_factor") is not None:
        row["price_factor"] = float(resolution["resolved_price_factor"])
    if resolution.get("resolved_share_factor") is not None:
        row["share_factor"] = float(resolution["resolved_share_factor"])
    row["review_status"] = resolution.get("review_classification") or resolution.get("review_status") or row.get("review_status")
    row["review_classification"] = resolution.get("review_classification")
    row["classification_confidence"] = resolution.get("classification_confidence")
    row["factor_quality"] = resolution.get("factor_quality")
    row["resolution_type"] = resolution.get("resolution_type")
    row["evidence_references"] = resolution.get("evidence_references") or []
    row["review_rationale"] = resolution.get("rationale")
    for key in (
        "bonus_ratio", "rights_ratio", "rights_subscription_price", "post_share_count_per_old_share",
        "cash_contribution_per_old_share", "rights_entitlement_basis", "bonus_ratio_numerator",
        "bonus_ratio_denominator", "eligibility_scope", "pre_event_total_shares", "post_event_total_shares",
        "public_holder_share_factor", "promoter_holder_share_factor",
    ):
        row[key] = resolution.get(key)
    notes = [value for value in (row.get("notes"), resolution.get("resolution_type")) if value]
    row["notes"] = ";".join(notes) if notes else None
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default="data/raw/nse/corporate_actions/corporate_actions_2006_2026.json")
    parser.add_argument("--master", default="data/canonical/security_master.jsonl")
    parser.add_argument("--out", default="data/canonical/corporate_actions.jsonl")
    parser.add_argument("--resolutions", default="data/reference/corporate_action_resolutions.yaml")
    args = parser.parse_args()
    raw = json.loads(Path(args.raw).read_text(encoding="utf-8"))
    master = read_jsonl(args.master)
    resolutions = load_resolutions(args.resolutions)
    isin_to_security = {row["isin"]: row["security_id"] for row in master if row.get("isin") and row.get("series") == "EQ"}
    output = []
    for index, item in enumerate(raw):
        if item.get("series") != "EQ":
            continue
        subject = (item.get("subject") or "").strip()
        event_type = classify(subject)
        numerator, denominator, ratio_raw = ratio(subject)
        old_face_value, new_face_value, face_price_factor = face_value_transition(subject, event_type)
        cash_dividend_per_share, dividend_amount_quality = dividend_amount(subject, item.get("faceVal"), event_type)
        unsupported_rights_component = has_unsupported_rights_component(subject, event_type)
        event_date = parse_date(item.get("exDate")) or parse_date(item.get("recDate"))
        if not event_date:
            continue
        price_factor = None
        share_factor = None
        if event_type == "BONUS" and numerator is not None and denominator and not unsupported_rights_component:
            share_factor = (numerator + denominator) / denominator
            price_factor = 1.0 / share_factor
            if face_price_factor is not None:
                price_factor *= face_price_factor
                share_factor /= face_price_factor
        if event_type in {"SPLIT", "REVERSE_SPLIT"} and face_price_factor is not None and not unsupported_rights_component:
            price_factor = face_price_factor
            share_factor = 1.0 / face_price_factor
        notes = "UNSUPPORTED_COMPOSITE_RIGHTS_COMPONENT" if unsupported_rights_component else None
        event_id = f"NSE_CA_{index:06d}"
        row = {"event_id": event_id, "security_id": isin_to_security.get(item.get("isin")), "issuer_id": None, "exchange": "NSE", "symbol_at_event": item.get("symbol"), "isin": item.get("isin"), "series": item.get("series"), "event_type": event_type, "event_date": event_date, "ex_date": parse_date(item.get("exDate")), "record_date": parse_date(item.get("recDate")), "subject": subject, "face_value": item.get("faceVal"), "old_face_value": old_face_value, "new_face_value": new_face_value, "cash_dividend_per_share": cash_dividend_per_share, "dividend_currency": "INR" if cash_dividend_per_share is not None else None, "dividend_amount_quality": dividend_amount_quality, "ratio_raw": ratio_raw, "ratio_numerator": numerator, "ratio_denominator": denominator, "price_factor": price_factor, "share_factor": share_factor, "source": "NSE_OFFICIAL_CORPORATE_ACTION_FEED", "source_file_id": Path(args.raw).name, "source_quality": "OFFICIAL_EXCHANGE_ACTION_FEED", "review_status": "FACTOR_REVIEW_REQUIRED" if unsupported_rights_component else ("RESOLVED_BY_ISIN" if item.get("isin") in isin_to_security else "IDENTITY_REVIEW_REQUIRED"), "notes": notes, "review_classification": None, "classification_confidence": None, "factor_quality": None, "resolution_type": None, "evidence_references": [], "review_rationale": None, "bonus_ratio": None, "rights_ratio": None, "rights_subscription_price": None, "post_share_count_per_old_share": None, "cash_contribution_per_old_share": None, "rights_entitlement_basis": None, "bonus_ratio_numerator": None, "bonus_ratio_denominator": None, "eligibility_scope": None, "pre_event_total_shares": None, "post_event_total_shares": None, "public_holder_share_factor": None, "promoter_holder_share_factor": None}
        output.append(apply_resolution(row, resolutions.get(event_id)))
    write_jsonl(args.out, output, overwrite=True)
    print(json.dumps({"events": len(output), "linked_security_ids": sum(row["security_id"] is not None for row in output), "unresolved_identity": sum(row["security_id"] is None for row in output)}, sort_keys=True))


if __name__ == "__main__":
    main()
