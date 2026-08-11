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
    dividend_events = []
    for event in json_rows(Path(args.events)):
        factor = event.get("price_factor")
        if event.get("security_id") and factor is not None and factor > 0:
            events.setdefault(event["security_id"], []).append((event["event_date"], float(factor), event["event_id"]))
        amount = event.get("cash_dividend_per_share")
        if event.get("security_id") and event.get("event_type") == "DIVIDEND" and amount is not None and float(amount) >= 0:
            dividend_events.append((event["security_id"], event["event_date"], float(amount), event["event_id"]))
    for values in events.values():
        values.sort()
    dividend_targets = {(security_id, event_date) for security_id, event_date, _, _ in dividend_events}
    ex_closes = {}
    for row in json_rows(Path(args.prices)):
        key = (row["security_id"], row["date"])
        if key in dividend_targets and row.get("raw_close") is not None and row["raw_close"] > 0:
            ex_closes[key] = float(row["raw_close"])
    dividends = {}
    for security_id, event_date, amount, event_id in dividend_events:
        close = ex_closes.get((security_id, event_date))
        if close is not None:
            dividends.setdefault(security_id, []).append((event_date, (close + amount) / close, event_id))
    for values in dividends.values():
        values.sort()
    schema = pa.schema([
        pa.field("date", pa.string()), pa.field("security_id", pa.string()), pa.field("listing_episode_id", pa.string()), pa.field("symbol_at_date", pa.string()),
        pa.field("raw_close", pa.float64()),
        pa.field("research_adjusted_close", pa.float64()), pa.field("research_adjustment_factor", pa.float64()),
        pa.field("price_return_adjusted_close", pa.float64()), pa.field("price_return_adjustment_factor", pa.float64()),
        pa.field("adjustment_quality", pa.string()), pa.field("source_event_ids", pa.list_(pa.string())),
        pa.field("research_adjusted_close_total_return", pa.float64()), pa.field("research_total_return_factor", pa.float64()),
        pa.field("total_return_adjusted_close", pa.float64()), pa.field("total_return_factor", pa.float64()),
        pa.field("total_return_quality", pa.string()), pa.field("total_return_event_ids", pa.list_(pa.string())),
    ])
    target = Path(args.out)
    temp = target.with_suffix(target.suffix + ".tmp")
    writer = pq.ParquetWriter(temp, schema, compression="zstd", use_dictionary=True)
    batch = []
    counts = {"NO_ADJUSTMENT_REQUIRED": 0, "PRICE_ACTION_ADJUSTED_VERIFIED": 0}
    try:
        for row in json_rows(Path(args.prices)):
            actions = events.get(row["security_id"], [])
            dates = [item[0] for item in actions]
            index = bisect.bisect_right(dates, row["date"])
            applicable = actions[index:]
            factor = math.prod(item[1] for item in applicable) if applicable else 1.0
            quality = "PRICE_ACTION_ADJUSTED_VERIFIED" if applicable else "NO_ADJUSTMENT_REQUIRED"
            dividend_actions = dividends.get(row["security_id"], [])
            dividend_dates = [item[0] for item in dividend_actions]
            dividend_index = bisect.bisect_right(dividend_dates, row["date"])
            applicable_dividends = dividend_actions[dividend_index:]
            total_factor = math.prod(item[1] for item in applicable_dividends) if applicable_dividends else 1.0
            total_quality = "TOTAL_RETURN_PARTIAL"
            counts[quality] += 1
            raw = row.get("raw_close")
            price_return_close = raw * factor if raw is not None else None
            total_return_close = raw * factor * total_factor if raw is not None else None
            batch.append({"date": row["date"], "security_id": row["security_id"], "listing_episode_id": row["listing_episode_id"], "symbol_at_date": row["symbol_at_date"], "raw_close": raw, "research_adjusted_close": price_return_close, "research_adjustment_factor": factor, "price_return_adjusted_close": price_return_close, "price_return_adjustment_factor": factor, "adjustment_quality": quality, "source_event_ids": [item[2] for item in applicable], "research_adjusted_close_total_return": total_return_close, "research_total_return_factor": factor * total_factor, "total_return_adjusted_close": total_return_close, "total_return_factor": factor * total_factor, "total_return_quality": total_quality, "total_return_event_ids": [item[2] for item in applicable_dividends]})
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
