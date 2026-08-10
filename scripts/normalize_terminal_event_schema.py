#!/usr/bin/env python3
"""Write terminal events with an explicit nullable public schema."""

from __future__ import annotations

import argparse
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


SCHEMA = pa.schema([
    pa.field("company_name", pa.string()),
    pa.field("event_id", pa.string()),
    pa.field("event_quality", pa.string()),
    pa.field("historical_symbol", pa.string()),
    pa.field("identity_match_quality", pa.string()),
    pa.field("issuer_id", pa.string()),
    pa.field("notes", pa.string()),
    pa.field("security_id", pa.string()),
    pa.field("source", pa.string()),
    pa.field("terminal_event_date", pa.string()),
    pa.field("terminal_event_type", pa.string()),
    pa.field("terminal_value", pa.float64()),
    pa.field("terminal_value_basis", pa.string()),
    pa.field("terminal_value_quality", pa.string()),
])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    rows = pq.read_table(args.input).to_pylist()
    normalized = []
    for row in rows:
        normalized.append({
            name: (float(row[name]) if name == "terminal_value" and row.get(name) is not None else row.get(name))
            for name in SCHEMA.names
        })
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(normalized, schema=SCHEMA), path, compression="zstd")
    print(f"rows={len(normalized)} schema={SCHEMA}")


if __name__ == "__main__":
    main()
