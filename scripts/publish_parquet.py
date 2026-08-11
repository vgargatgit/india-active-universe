from __future__ import annotations

import argparse
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from india_active_universe.profiles import TARGET_RELEASE_ID


def json_rows(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def infer_schema(rows: list[dict]) -> pa.Schema:
    names = []
    values = {}
    for row in rows:
        for name, value in row.items():
            if name not in values:
                names.append(name)
                values[name] = []
            if value is not None:
                values[name].append(value)
    fields = []
    for name in names:
        sample = values[name][0] if values[name] else ""
        if isinstance(sample, bool):
            dtype = pa.bool_()
        elif isinstance(sample, int):
            dtype = pa.int64()
        elif isinstance(sample, float):
            dtype = pa.float64()
        elif isinstance(sample, list):
            dtype = pa.list_(pa.string())
        else:
            dtype = pa.string()
        fields.append(pa.field(name, dtype, nullable=True))
    return pa.schema(fields)


def publish(source: Path, target: Path, batch_size: int = 25_000, schema_if_empty: pa.Schema | None = None) -> int:
    iterator = json_rows(source)
    first = []
    for _ in range(batch_size):
        try:
            first.append(next(iterator))
        except StopIteration:
            break
    if not first:
        if schema_if_empty is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise FileExistsError(f"Immutable published artifact already exists: {target}")
            pq.write_table(pa.Table.from_pylist([], schema=schema_if_empty), target, compression="zstd", use_dictionary=True)
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(f"Immutable published artifact already exists: {target}")
    schema = infer_schema(first)
    writer = pq.ParquetWriter(target, schema, compression="zstd", use_dictionary=True)
    count = 0
    try:
        batch = first
        while batch:
            table = pa.Table.from_pylist(batch, schema=schema)
            writer.write_table(table)
            count += len(batch)
            batch = []
            for _ in range(batch_size):
                try:
                    batch.append(next(iterator))
                except StopIteration:
                    break
    finally:
        writer.close()
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data")
    parser.add_argument("--release", default=f"releases/{TARGET_RELEASE_ID}")
    args = parser.parse_args()
    data, release = Path(args.data), Path(args.release)
    mappings = {
        "security_master.jsonl": "security_master.parquet",
        "symbol_history.jsonl": "symbol_history.parquet",
        "security_id_migration.jsonl": "security_id_migration.parquet",
        "unresolved_observed_trading.jsonl": "unresolved_observed_trading.parquet",
        "daily_prices_raw.jsonl": "daily_prices_raw.parquet",
        "active_universe_daily.jsonl": "active_universe_daily.parquet",
        "liquidity_features.jsonl": "liquidity_features.parquet",
        "data_quality_findings.jsonl": "data_quality_findings.parquet",
    }
    schemas_if_empty = {
        "unresolved_observed_trading.jsonl": pa.schema([
            pa.field("date", pa.string()), pa.field("exchange", pa.string()), pa.field("symbol", pa.string()),
            pa.field("series", pa.string()), pa.field("isin", pa.string()), pa.field("company_name", pa.string()),
            pa.field("raw_open", pa.float64()), pa.field("raw_high", pa.float64()), pa.field("raw_low", pa.float64()),
            pa.field("raw_close", pa.float64()), pa.field("volume", pa.int64()), pa.field("traded_value", pa.float64()),
            pa.field("source_file_id", pa.string()), pa.field("source_sha256", pa.string()), pa.field("source_quality", pa.string()),
            pa.field("resolution_status", pa.string()), pa.field("candidate_security_ids", pa.list_(pa.string())),
        ]),
    }
    counts = {}
    for source_name, target_name in mappings.items():
        source = next(data.rglob(source_name), None)
        if source is None:
            raise FileNotFoundError(source_name)
        counts[target_name] = publish(source, release / target_name, schema_if_empty=schemas_if_empty.get(source_name))
    (release / "published_counts.json").write_text(json.dumps(counts, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(counts, sort_keys=True))


if __name__ == "__main__":
    main()
