from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--master", default="data/canonical/security_master.jsonl")
    parser.add_argument("--coverage-end")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    last_seen = defaultdict(lambda: {"last_date": None, "symbol": None, "issuer_id": None})
    with Path(args.master).open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            sid = row["security_id"]
            if last_seen[sid]["last_date"] is None or row["last_seen"] > last_seen[sid]["last_date"]:
                last_seen[sid] = {"last_date": row["last_seen"], "symbol": row.get("symbol"), "issuer_id": row.get("issuer_id")}
    coverage_end = args.coverage_end or max(row["last_date"] for row in last_seen.values())
    rows = []
    for index, (security_id, row) in enumerate(sorted(last_seen.items())):
        if row["last_date"] < coverage_end:
            rows.append({"event_id": f"OBS_GAP_{index:06d}", "security_id": security_id, "issuer_id": row["issuer_id"], "terminal_event_date": row["last_date"], "historical_symbol": row["symbol"], "terminal_event_type": "UNKNOWN_TERMINAL_EVENT", "terminal_value": None, "terminal_value_basis": None, "terminal_value_quality": "UNKNOWN", "event_quality": "UNRESOLVED", "source": "OBSERVATION_COVERAGE_GAP", "notes": f"No qualifying official observation after {row['last_date']} through coverage end {coverage_end}; not classified as delisted."})
    schema = pa.schema([pa.field("event_id", pa.string()), pa.field("security_id", pa.string()), pa.field("issuer_id", pa.string()), pa.field("terminal_event_date", pa.string()), pa.field("historical_symbol", pa.string()), pa.field("terminal_event_type", pa.string()), pa.field("terminal_value", pa.float64()), pa.field("terminal_value_basis", pa.string()), pa.field("terminal_value_quality", pa.string()), pa.field("event_quality", pa.string()), pa.field("source", pa.string()), pa.field("notes", pa.string())])
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), args.out, compression="zstd", use_dictionary=True)
    print(json.dumps({"unknown_terminal_events": len(rows), "coverage_end": coverage_end}, sort_keys=True))


if __name__ == "__main__":
    main()
