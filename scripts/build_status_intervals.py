from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--master", default="data/canonical/security_master.jsonl")
    parser.add_argument("--terminal-events", required=True)
    parser.add_argument("--coverage-end")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    master: dict[str, dict] = {}
    with Path(args.master).open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            sid = row["security_id"]
            current = master.get(sid)
            if current is None or row["last_seen"] > current["last_seen"]:
                master[sid] = row
    coverage_end = args.coverage_end or max(row["last_seen"] for row in master.values())
    events = defaultdict(list)
    for row in pq.read_table(args.terminal_events).to_pylist():
        if row.get("security_id") and row.get("terminal_event_type") == "COMPULSORY_DELISTING" and row.get("terminal_event_date") and row.get("event_quality") == "OFFICIAL_NSE_NOTICE":
            events[row["security_id"]].append(row)
    output = []
    for sid, row in sorted(master.items()):
        official = sorted(events.get(sid, []), key=lambda item: item["terminal_event_date"])
        if official:
            event = official[0]
            observed_end = date.fromisoformat(row["last_seen"])
            event_start = max(date.fromisoformat(event["terminal_event_date"]), observed_end + timedelta(days=1))
            active_end = (event_start - timedelta(days=1)).isoformat()
            output.append({"security_id": sid, "listing_episode_id": row["listing_episode_id"], "symbol": row.get("symbol"), "status_start": row["first_seen"], "status_end": active_end, "trading_status": "ACTIVE_TRADING", "status_quality": "OBSERVED_TRADING_RECORD", "source": "NSE_HISTORICAL_OBSERVATIONS", "source_reference": row.get("source_reference")})
            if event_start.isoformat() <= coverage_end:
                output.append({"security_id": sid, "listing_episode_id": row["listing_episode_id"], "symbol": row.get("symbol"), "status_start": event_start.isoformat(), "status_end": None, "trading_status": "DELISTED", "status_quality": "OFFICIAL_NSE_NOTICE", "source": event["source"], "source_reference": event["event_id"]})
        elif row["last_seen"] < coverage_end:
            output.append({"security_id": sid, "listing_episode_id": row["listing_episode_id"], "symbol": row.get("symbol"), "status_start": row["first_seen"], "status_end": row["last_seen"], "trading_status": "ACTIVE_TRADING", "status_quality": "OBSERVED_TRADING_RECORD", "source": "NSE_HISTORICAL_OBSERVATIONS", "source_reference": row.get("source_reference")})
            next_date = (date.fromisoformat(row["last_seen"]) + timedelta(days=1)).isoformat()
            output.append({"security_id": sid, "listing_episode_id": row["listing_episode_id"], "symbol": row.get("symbol"), "status_start": next_date, "status_end": coverage_end, "trading_status": "UNKNOWN_STATUS", "status_quality": "OBSERVATION_GAP_ONLY", "source": "OBSERVATION_COVERAGE_GAP", "source_reference": None})
        else:
            output.append({"security_id": sid, "listing_episode_id": row["listing_episode_id"], "symbol": row.get("symbol"), "status_start": row["first_seen"], "status_end": row["last_seen"], "trading_status": "ACTIVE_TRADING", "status_quality": "OBSERVED_TRADING_RECORD", "source": "NSE_HISTORICAL_OBSERVATIONS", "source_reference": row.get("source_reference")})
    schema = pa.schema([pa.field("security_id", pa.string()), pa.field("listing_episode_id", pa.string()), pa.field("symbol", pa.string()), pa.field("status_start", pa.string()), pa.field("status_end", pa.string()), pa.field("trading_status", pa.string()), pa.field("status_quality", pa.string()), pa.field("source", pa.string()), pa.field("source_reference", pa.string())])
    pq.write_table(pa.Table.from_pylist(output, schema=schema), args.out, compression="zstd", use_dictionary=True)
    print(json.dumps({"intervals": len(output), "active": sum(row["trading_status"] == "ACTIVE_TRADING" for row in output), "delisted": sum(row["trading_status"] == "DELISTED" for row in output), "unknown": sum(row["trading_status"] == "UNKNOWN_STATUS" for row in output)}, sort_keys=True))


if __name__ == "__main__":
    main()
