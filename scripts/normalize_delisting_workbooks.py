from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from india_active_universe.storage import write_jsonl


def clean(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def date_value(value: object) -> str | None:
    if pd.isna(value):
        return None
    return pd.Timestamp(value).date().isoformat()


def resolver(master: list[dict]):
    by_symbol: dict[str, list[dict]] = {}
    for row in master:
        by_symbol.setdefault(clean(row.get("symbol")), []).append(row)
    def resolve(symbol: object, point: str | None) -> tuple[str | None, str | None]:
        candidates = by_symbol.get(clean(symbol), [])
        if point:
            candidates = [row for row in candidates if row.get("effective_from", "") <= point <= (row.get("effective_to") or point)] or candidates
        ids = {row["security_id"] for row in candidates}
        if len(ids) == 1:
            return next(iter(ids)), "SYMBOL_DATE_MATCH"
        return (next(iter(ids)), "SYMBOL_AMBIGUOUS") if len(ids) == 1 else (None, "IDENTITY_REVIEW_REQUIRED")
    return resolve


def make_event(index: int, row: dict, event_type: str, source: str, resolve) -> dict:
    event_date = row.get("event_date")
    security_id, match_quality = resolve(row.get("symbol"), event_date)
    return {"event_id": f"NSE_TERM_{index:06d}", "security_id": security_id, "issuer_id": None, "terminal_event_date": event_date, "historical_symbol": row.get("symbol"), "company_name": row.get("company_name"), "terminal_event_type": event_type, "terminal_value": None, "terminal_value_basis": None, "terminal_value_quality": "UNKNOWN", "event_quality": "OFFICIAL_NSE_NOTICE" if security_id else "IDENTITY_REVIEW_REQUIRED", "identity_match_quality": match_quality, "source": source, "notes": row.get("notes")}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--master", default="data/canonical/security_master.jsonl")
    parser.add_argument("--raw-dir", default="data/raw/nse/delistings")
    parser.add_argument("--unknown", default="releases/india_equity_data_v0.4.0/terminal_events.parquet")
    parser.add_argument("--out", default="data/canonical/terminal_events.jsonl")
    args = parser.parse_args()
    master = json.loads("[" + ",".join(line for line in Path(args.master).read_text(encoding="utf-8").splitlines() if line) + "]")
    resolve = resolver(master)
    raw = Path(args.raw_dir)
    rows: list[dict] = []
    compulsory = pd.read_excel(raw / "DelistedCos_Buy_and_Sell.xls")
    for _, item in compulsory.iterrows():
        rows.append(make_event(len(rows), {"symbol": item.get("Symbol"), "company_name": item.get("Company Name"), "event_date": date_value(item.get("Date of delisting")), "notes": "Official NSE compulsory-delisted companies workbook"}, "COMPULSORY_DELISTING", "NSE_OFFICIAL_COMPULSORY_DELISTING_WORKBOOK", resolve))
    dissemination = pd.read_excel(raw / "List_of_companies_on_Dissemination_Board_20260714162536.xlsx")
    for _, item in dissemination.iterrows():
        rows.append(make_event(len(rows), {"symbol": item.get("Symbol"), "company_name": item.get("Name of the Company"), "event_date": None, "notes": "Official NSE dissemination-board workbook; date not supplied"}, "DISSEMINATION_BOARD", "NSE_OFFICIAL_DISSEMINATION_BOARD_WORKBOOK", resolve))
    removed = pd.read_excel(raw / "List_of_companies_removed_on_listing_20260610144610.xlsx")
    for _, item in removed.iterrows():
        rows.append(make_event(len(rows), {"symbol": item.get("Symbol"), "company_name": item.get("Name of the Company"), "event_date": None, "notes": "Official NSE removed-on-listing workbook; date not supplied"}, "REMOVED_ON_LISTING", "NSE_OFFICIAL_REMOVED_ON_LISTING_WORKBOOK", resolve))
    for item in pq.read_table(args.unknown).to_pylist():
        rows.append(item)
    write_jsonl(args.out, rows, overwrite=True)
    print(json.dumps({"events": len(rows), "dated_official": sum(row.get("event_quality") == "OFFICIAL_NSE_NOTICE" for row in rows), "identity_review": sum(row.get("event_quality") == "IDENTITY_REVIEW_REQUIRED" for row in rows), "unknown_gap": sum(row.get("source") == "OBSERVATION_COVERAGE_GAP" for row in rows)}, sort_keys=True))


if __name__ == "__main__":
    main()
