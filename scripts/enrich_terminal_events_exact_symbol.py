#!/usr/bin/env python3
"""Resolve terminal notices only when a symbol maps to one observed security."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq


def d(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def write(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path, compression="zstd")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--terminal-events", required=True)
    parser.add_argument("--master", required=True)
    parser.add_argument("--intervals", required=True)
    parser.add_argument("--terminal-events-out", required=True)
    parser.add_argument("--intervals-out", required=True)
    args = parser.parse_args()
    con = duckdb.connect()

    master_columns = [r[0] for r in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [args.master]).fetchall()]
    masters = [dict(zip(master_columns, r)) for r in con.execute("SELECT * FROM read_parquet(?)", [args.master]).fetchall()]
    by_symbol: dict[str, list[dict]] = {}
    for row in masters:
        if row.get("exchange") == "NSE" and row.get("instrument_type") == "ORDINARY_EQUITY":
            by_symbol.setdefault(row.get("symbol"), []).append(row)

    event_columns = [r[0] for r in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [args.terminal_events]).fetchall()]
    events = [dict(zip(event_columns, r)) for r in con.execute("SELECT * FROM read_parquet(?)", [args.terminal_events]).fetchall()]
    resolved = 0
    for event in events:
        if event.get("security_id") or event.get("terminal_event_type") not in {
            "COMPULSORY_DELISTING", "VOLUNTARY_DELISTING", "UNKNOWN_TERMINAL_EVENT"
        }:
            continue
        event_date = d(event.get("terminal_event_date"))
        candidates = {row["security_id"]: row for row in by_symbol.get(event.get("historical_symbol"), [])}
        if event_date is None or len(candidates) != 1:
            continue
        row = next(iter(candidates.values()))
        if d(row.get("last_seen")) is None or d(row["last_seen"]) >= event_date:
            continue
        event.update(
            security_id=row["security_id"],
            issuer_id=row.get("issuer_id"),
            identity_match_quality="EXACT_SYMBOL_AFTER_OBSERVED_COVERAGE",
            event_quality="OFFICIAL_NSE_NOTICE",
            notes=(event.get("notes") or "") + "; unique NSE symbol and event follows observed coverage",
        )
        resolved += 1

    interval_columns = [r[0] for r in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [args.intervals]).fetchall()]
    intervals = [dict(zip(interval_columns, r)) for r in con.execute("SELECT * FROM read_parquet(?)", [args.intervals]).fetchall()]
    for event in events:
        if event.get("identity_match_quality") != "EXACT_SYMBOL_AFTER_OBSERVED_COVERAGE":
            continue
        event_date = d(event["terminal_event_date"])
        new: list[dict] = []
        for row in intervals:
            if row["security_id"] != event["security_id"]:
                new.append(row)
                continue
            start, end = d(row["status_start"]), d(row["status_end"])
            if not (start <= event_date <= end):
                new.append(row)
                continue
            if start < event_date:
                before = dict(row)
                before["status_end"] = date.fromordinal(event_date.toordinal() - 1).isoformat()
                new.append(before)
            after = dict(row)
            after["status_start"] = event_date.isoformat()
            after["trading_status"] = "DELISTED"
            after["status_quality"] = "OFFICIAL_NSE_DELISTING_NOTICE_EXACT_SYMBOL"
            after["source"] = event.get("source") or "NSE_OFFICIAL_NOTICE"
            after["source_reference"] = event.get("event_id")
            new.append(after)
        intervals = new

    write(events, Path(args.terminal_events_out))
    write(sorted(intervals, key=lambda r: (r["security_id"], r["status_start"])), Path(args.intervals_out))
    print(f"resolved_terminal_events={resolved} intervals={len(intervals)}")


if __name__ == "__main__":
    main()
