#!/usr/bin/env python3
"""Resolve exact suspension identities and overlay verified suspension intervals."""

from __future__ import annotations

import argparse
import re
import unicodedata
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq


def normalize_name(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    text = re.sub(r"[^A-Za-z0-9]+", " ", text).upper()
    text = re.sub(r"\b(LIMITED|LTD)\b", "LTD", text)
    text = re.sub(r"\b(COMPANY|CO)\b", "CO", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def write_table(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path, compression="zstd")


def resolve_events(con: duckdb.DuckDBPyConnection, events_path: str, master_path: str) -> list[dict]:
    masters = con.execute(
        """
        SELECT DISTINCT security_id, issuer_id, listing_episode_id, symbol, series,
               company_name, identity_quality
        FROM read_parquet(?)
        WHERE exchange = 'NSE'
          AND instrument_type = 'ORDINARY_EQUITY'
          AND series IN ('EQ', 'BE')
          AND company_name IS NOT NULL
        """,
        [master_path],
    ).fetchall()
    by_name: dict[str, list[tuple]] = {}
    for row in masters:
        name = normalize_name(row[5])
        if len(name) >= 8:
            by_name.setdefault(name, []).append(row)

    events = con.execute("SELECT * FROM read_parquet(?) ORDER BY evidence_id", [events_path]).fetchall()
    columns = [row[0] for row in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [events_path]).fetchall()]
    result: list[dict] = []
    for values in events:
        event = dict(zip(columns, values))
        text = normalize_name(event.get("text_excerpt"))
        candidates: dict[str, tuple] = {}
        for name, rows in by_name.items():
            if name in text:
                for row in rows:
                    candidates[row[0]] = row
        resolved = list(candidates.values())
        if len(resolved) == 1:
            row = resolved[0]
            event.update(
                security_id=row[0],
                issuer_id=row[1],
                listing_episode_id=row[2],
                symbol=row[3],
                series=row[4],
                resolved_company_name=row[5],
                identity_quality="RECONSTRUCTED_HIGH_CONFIDENCE",
                identity_match_quality="EXACT_NORMALIZED_COMPANY_NAME_UNIQUE_SECURITY",
            )
        else:
            event.update(
                security_id=None,
                issuer_id=None,
                listing_episode_id=None,
                symbol=None,
                series=None,
                resolved_company_name=None,
                identity_quality="UNRESOLVED",
                identity_match_quality=(
                    "NO_UNIQUE_EXACT_MATCH" if not resolved else "AMBIGUOUS_EXACT_MATCH"
                ),
            )
        event["candidate_security_count"] = len(resolved)
        event["resolution_method"] = "EXACT_NORMALIZED_COMPANY_NAME" if resolved else None
        result.append(event)
    return result


def overlay_intervals(
    con: duckdb.DuckDBPyConnection,
    base_path: str,
    prices_path: str,
    resolved_events: list[dict],
) -> list[dict]:
    base_columns = [row[0] for row in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [base_path]).fetchall()]
    base_rows = [dict(zip(base_columns, row)) for row in con.execute("SELECT * FROM read_parquet(?)", [base_path]).fetchall()]
    starts = [
        e for e in resolved_events
        if e.get("event_type") == "SUSPENSION_START"
        and e.get("security_id")
        and e.get("effective_date")
    ]
    for event in starts:
        security_id = event["security_id"]
        start = parse_date(event["effective_date"])
        next_trade_row = con.execute(
            "SELECT min(date) FROM read_parquet(?) WHERE security_id = ? AND date >= ?",
            [prices_path, security_id, start.isoformat()],
        ).fetchone()
        next_trade = parse_date(next_trade_row[0]) if next_trade_row and next_trade_row[0] else None
        if next_trade is None or next_trade <= start:
            continue
        end = next_trade - timedelta(days=1)
        new_rows: list[dict] = []
        inserted = False
        for row in base_rows:
            if row["security_id"] != security_id:
                new_rows.append(row)
                continue
            row_start = parse_date(row["status_start"])
            row_end = parse_date(row["status_end"])
            if row_end < start or row_start > end:
                new_rows.append(row)
                continue
            if row_start < start:
                before = dict(row)
                before["status_end"] = (start - timedelta(days=1)).isoformat()
                new_rows.append(before)
            suspended = dict(row)
            suspended["status_start"] = max(row_start, start).isoformat()
            suspended["status_end"] = min(row_end, end).isoformat()
            suspended["trading_status"] = "SUSPENDED"
            suspended["status_quality"] = "OFFICIAL_NSE_SUSPENSION_NOTICE_EXACT_IDENTITY"
            suspended["source"] = "NSE_OFFICIAL_PRESS_ARCHIVE"
            suspended["source_reference"] = event["evidence_id"]
            new_rows.append(suspended)
            if row_end > end:
                after = dict(row)
                after["status_start"] = (end + timedelta(days=1)).isoformat()
                new_rows.append(after)
            inserted = True
        if inserted:
            base_rows = new_rows
    return sorted(base_rows, key=lambda row: (row["security_id"], row["status_start"], row["status_end"]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", required=True)
    parser.add_argument("--master", required=True)
    parser.add_argument("--base-intervals", required=True)
    parser.add_argument("--prices", required=True)
    parser.add_argument("--events-out", required=True)
    parser.add_argument("--intervals-out", required=True)
    args = parser.parse_args()

    con = duckdb.connect()
    events = resolve_events(con, args.events, args.master)
    intervals = overlay_intervals(con, args.base_intervals, args.prices, events)
    write_table(events, Path(args.events_out))
    write_table(intervals, Path(args.intervals_out))
    print(f"resolved_events={sum(bool(e.get('security_id')) for e in events)} total_events={len(events)}")
    print(f"intervals={len(intervals)} suspended={sum(r['trading_status'] == 'SUSPENDED' for r in intervals)}")


if __name__ == "__main__":
    main()
