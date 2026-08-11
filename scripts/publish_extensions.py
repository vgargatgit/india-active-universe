from __future__ import annotations

import argparse
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def rows(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def copy_parquet(source: Path, target: Path) -> int:
    if not source.exists():
        raise FileNotFoundError(source)
    if target.exists():
        raise FileExistsError(f"Immutable published artifact already exists: {target}")
    table = pq.read_table(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, target, compression="zstd", use_dictionary=True)
    return table.num_rows


def write_stream(source: Path, target: Path, transform, schema: pa.Schema, batch_size: int = 25_000) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    writer = pq.ParquetWriter(target, schema, compression="zstd", use_dictionary=True)
    batch, count = [], 0
    try:
        for row in rows(source):
            batch.append(transform(row))
            if len(batch) >= batch_size:
                writer.write_table(pa.Table.from_pylist(batch, schema=schema))
                count += len(batch)
                batch = []
        if batch:
            writer.write_table(pa.Table.from_pylist(batch, schema=schema))
            count += len(batch)
    finally:
        writer.close()
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data")
    parser.add_argument("--release", required=True)
    parser.add_argument("--corporate-actions", required=True)
    parser.add_argument("--terminal-events", required=True)
    args = parser.parse_args()
    data, release = Path(args.data), Path(args.release)
    raw = data / "canonical/daily_prices_raw.jsonl"
    adjusted_schema = pa.schema([
        pa.field("date", pa.string()), pa.field("security_id", pa.string()), pa.field("listing_episode_id", pa.string()), pa.field("symbol_at_date", pa.string()), pa.field("raw_close", pa.float64()), pa.field("research_adjusted_close", pa.float64()), pa.field("research_adjustment_factor", pa.float64()), pa.field("price_return_adjusted_close", pa.float64()), pa.field("price_return_adjustment_factor", pa.float64()), pa.field("adjustment_quality", pa.string()), pa.field("source_event_ids", pa.list_(pa.string())),
    ])
    adjusted_count = write_stream(raw, release / "daily_prices_adjusted.parquet", lambda row: {"date": row["date"], "security_id": row["security_id"], "listing_episode_id": row["listing_episode_id"], "symbol_at_date": row["symbol_at_date"], "raw_close": row.get("raw_close"), "research_adjusted_close": row.get("raw_close"), "research_adjustment_factor": 1.0, "price_return_adjusted_close": row.get("raw_close"), "price_return_adjustment_factor": 1.0, "adjustment_quality": "NO_ADJUSTMENT_REQUIRED", "source_event_ids": []}, adjusted_schema)
    universe = data / "derived/active_universe_daily.jsonl"
    status_schema = pa.schema([pa.field("date", pa.string()), pa.field("security_id", pa.string()), pa.field("listing_episode_id", pa.string()), pa.field("symbol", pa.string()), pa.field("trading_status", pa.string()), pa.field("status_quality", pa.string()), pa.field("source_file_id", pa.string())])
    status_count = write_stream(universe, release / "trading_status.parquet", lambda row: {"date": row["date"], "security_id": row["security_id"], "listing_episode_id": row["listing_episode_id"], "symbol": row.get("symbol_at_date"), "trading_status": row.get("trading_status", "ACTIVE_TRADING"), "status_quality": "OBSERVED_TRADING_RECORD", "source_file_id": row.get("source_file_id")}, status_schema)
    corporate_actions_count = copy_parquet(Path(args.corporate_actions), release / "corporate_actions.parquet")
    terminal_events_count = copy_parquet(Path(args.terminal_events), release / "terminal_events.parquet")
    print(json.dumps({"adjusted_prices": adjusted_count, "trading_status": status_count, "corporate_actions": corporate_actions_count, "terminal_events": terminal_events_count}, sort_keys=True))


if __name__ == "__main__":
    main()
