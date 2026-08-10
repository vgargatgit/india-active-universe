from __future__ import annotations

import argparse
import bisect
import json
import math
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def json_rows(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prices", default="data/canonical/daily_prices_raw.jsonl")
    parser.add_argument("--events", default="data/canonical/corporate_actions.jsonl")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    events = {}
    for event in json_rows(Path(args.events)):
        factor = event.get("price_factor")
        if event.get("security_id") and factor is not None and factor > 0:
            events.setdefault(event["security_id"], []).append((event["event_date"], float(factor), event["event_id"]))
    for values in events.values():
        values.sort()
    schema = pa.schema([pa.field("date", pa.string()), pa.field("security_id", pa.string()), pa.field("listing_episode_id", pa.string()), pa.field("symbol_at_date", pa.string()), pa.field("raw_close", pa.float64()), pa.field("research_adjusted_close", pa.float64()), pa.field("research_adjustment_factor", pa.float64()), pa.field("adjustment_quality", pa.string()), pa.field("source_event_ids", pa.list_(pa.string()))])
    target = Path(args.out)
    temp = target.with_suffix(target.suffix + ".tmp")
    writer = pq.ParquetWriter(temp, schema, compression="zstd", use_dictionary=True)
    batch = []
    counts = {"RAW_ONLY": 0, "PRICE_ACTION_ADJUSTED": 0}
    try:
        for row in json_rows(Path(args.prices)):
            actions = events.get(row["security_id"], [])
            dates = [item[0] for item in actions]
            index = bisect.bisect_right(dates, row["date"])
            applicable = actions[index:]
            factor = math.prod(item[1] for item in applicable) if applicable else 1.0
            quality = "PRICE_ACTION_ADJUSTED" if applicable else "RAW_ONLY"
            counts[quality] += 1
            raw = row.get("raw_close")
            batch.append({"date": row["date"], "security_id": row["security_id"], "listing_episode_id": row["listing_episode_id"], "symbol_at_date": row["symbol_at_date"], "raw_close": raw, "research_adjusted_close": raw * factor if raw is not None else None, "research_adjustment_factor": factor, "adjustment_quality": quality, "source_event_ids": [item[2] for item in applicable]})
            if len(batch) >= 25_000:
                writer.write_table(pa.Table.from_pylist(batch, schema=schema))
                batch = []
        if batch:
            writer.write_table(pa.Table.from_pylist(batch, schema=schema))
    finally:
        writer.close()
    temp.replace(target)
    print(json.dumps(counts, sort_keys=True))


if __name__ == "__main__":
    main()
