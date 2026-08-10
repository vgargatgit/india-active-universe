#!/usr/bin/env python3
"""Apply conservative instrument classification to release Parquet artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from india_active_universe.pipeline import classify_instrument_type


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    source, target = Path(args.release), Path(args.out)
    target.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()

    master = pq.read_table(source / "security_master.parquet").to_pylist()
    classification_candidates: dict[str, set[str]] = {}
    for row in master:
        row["instrument_type"] = classify_instrument_type(row.get("symbol"), row.get("company_name"))
        classification_candidates.setdefault(row["security_id"], set()).add(row["instrument_type"])
    classifications = {}
    for security_id, candidates in classification_candidates.items():
        nonordinary = candidates - {"ORDINARY_EQUITY"}
        classifications[security_id] = next(iter(nonordinary)) if len(nonordinary) == 1 else ("UNKNOWN" if len(nonordinary) > 1 else "ORDINARY_EQUITY")
    for row in master:
        row["instrument_type"] = classifications[row["security_id"]]
    pq.write_table(pa.Table.from_pylist(master), target / "security_master.parquet", compression="zstd")

    map_path = target / "_instrument_map.parquet"
    pq.write_table(pa.Table.from_pylist([{"security_id": key, "instrument_type": value} for key, value in classifications.items()]), map_path, compression="zstd")
    try:
        for name in ("daily_prices_raw.parquet", "liquidity_features.parquet"):
            input_path = (source / name).as_posix().replace("'", "''")
            mapping_path = map_path.as_posix().replace("'", "''")
            output_path = (target / name).as_posix().replace("'", "''")
            con.execute(
                f"""COPY (
                    SELECT p.* EXCLUDE (instrument_type), m.instrument_type
                    FROM read_parquet('{input_path}') p
                    LEFT JOIN read_parquet('{mapping_path}') m USING (security_id)
                ) TO '{output_path}' (FORMAT PARQUET, COMPRESSION ZSTD)""",
            )
        input_path = (source / "active_universe_daily.parquet").as_posix().replace("'", "''")
        output_path = (target / "active_universe_daily.parquet").as_posix().replace("'", "''")
        con.execute(
            f"""COPY (
                SELECT p.* EXCLUDE (instrument_type), m.instrument_type
                FROM read_parquet('{input_path}') p
                JOIN read_parquet('{mapping_path}') m USING (security_id)
                WHERE m.instrument_type = 'ORDINARY_EQUITY'
            ) TO '{output_path}' (FORMAT PARQUET, COMPRESSION ZSTD)""",
        )
    finally:
        map_path.unlink(missing_ok=True)
    print(f"security_rows={len(master)} etf_rows={sum(r['instrument_type'] == 'ETF' for r in master)}")


if __name__ == "__main__":
    main()
