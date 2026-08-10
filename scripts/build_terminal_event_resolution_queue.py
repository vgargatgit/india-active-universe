#!/usr/bin/env python3
"""Build a terminal-event review queue for security IDs supplied by downstream holdings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--holdings", required=True, help="Text or CSV file with one security_id per line.")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    holdings = set()
    for line in Path(args.holdings).read_text(encoding="utf-8").splitlines():
        value = line.strip().split(",", 1)[0].strip()
        if value and value.lower() not in {"security_id", "id"}:
            holdings.add(value)
    release = Path(args.release).resolve()
    sql_release = str(release).replace("'", "''")
    connection = duckdb.connect()
    try:
        rows = connection.execute(f"""
          WITH last_price AS (
            SELECT security_id, raw_close AS last_observed_price
            FROM read_parquet('{sql_release}/daily_prices_raw.parquet') p
            WHERE CAST(date AS DATE) = (
              SELECT MAX(CAST(date AS DATE)) FROM read_parquet('{sql_release}/daily_prices_raw.parquet') q
              WHERE q.security_id = p.security_id
            )
          )
          SELECT e.*, l.last_observed_price
          FROM read_parquet('{sql_release}/terminal_events.parquet') e
          LEFT JOIN last_price l USING (security_id)
          WHERE e.security_id IN ({','.join('?' for _ in holdings)})
          ORDER BY e.security_id, e.terminal_event_date
        """, list(holdings)).fetchall() if holdings else []
        columns = [item[0] for item in connection.execute(f"DESCRIBE SELECT e.*, l.last_observed_price FROM read_parquet('{sql_release}/terminal_events.parquet') e LEFT JOIN (SELECT security_id, MAX(raw_close) AS last_observed_price FROM read_parquet('{sql_release}/daily_prices_raw.parquet') GROUP BY security_id) l USING(security_id)").fetchall()]
    finally:
        connection.close()
    output = []
    for values in rows:
        event = dict(zip(columns, values))
        last_price = event.pop("last_observed_price", None)
        common = {"security_id": event.get("security_id"), "event_id": event.get("event_id"), "terminal_event_type": event.get("terminal_event_type")}
        event["recovery_scenarios"] = [
            {"scenario": "ZERO_RECOVERY", "value": 0.0, "canonical": False},
            {"scenario": "LAST_OBSERVED_PRICE", "value": last_price, "canonical": False},
        ]
        if event.get("terminal_value") is not None:
            event["recovery_scenarios"].append({"scenario": "DOCUMENTED_VALUE", "value": event["terminal_value"], "canonical": True})
        output.append({**common, "event": event})
    Path(args.out).write_text(json.dumps({"holdings": sorted(holdings), "events": output}, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"holdings": len(holdings), "events": len(output), "out": args.out}, sort_keys=True))


if __name__ == "__main__":
    main()
