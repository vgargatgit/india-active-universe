#!/usr/bin/env python3
"""Create year-partitioned sidecar Parquet datasets for large release tables."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import duckdb

from india_active_universe.profiles import PARTITIONED_RELEASE_ARTIFACTS

DEFAULT_ARTIFACTS = PARTITIONED_RELEASE_ARTIFACTS


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sql_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def partition_one(connection: duckdb.DuckDBPyConnection, source: Path, target: Path, *, overwrite: bool) -> dict:
    if target.exists() and any(target.iterdir()):
        if not overwrite:
            raise FileExistsError(f"Partition target already exists: {target}")
        for child in target.rglob("*"):
            if child.is_file():
                child.unlink()
    target.mkdir(parents=True, exist_ok=True)
    source_sql = sql_path(source)
    target_sql = sql_path(target)
    connection.execute(f"""
        COPY (
          SELECT *, EXTRACT(YEAR FROM CAST(date AS DATE))::INTEGER AS partition_year
          FROM read_parquet('{source_sql}')
        )
        TO '{target_sql}'
        (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 25000, PARTITION_BY (partition_year))
    """)
    source_rows = connection.execute("SELECT COUNT(*) FROM read_parquet(?)", [str(source)]).fetchone()[0]
    partition_rows = connection.execute("SELECT COUNT(*) FROM read_parquet(?)", [str(target / "**/*.parquet")]).fetchone()[0]
    files = [
        {
            "path": str(path.relative_to(target)),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in sorted(target.rglob("*.parquet"))
    ]
    return {
        "source_artifact": source.name,
        "partitioned_path": target.name,
        "partition_column": "partition_year",
        "source_rows": source_rows,
        "partition_rows": partition_rows,
        "file_count": len(files),
        "bytes": sum(item["bytes"] for item in files),
        "files": files,
        "status": "PASS" if source_rows == partition_rows and files else "FAIL",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--out", default="partitioned_artifacts_manifest.json")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--artifacts", nargs="*", default=list(DEFAULT_ARTIFACTS))
    args = parser.parse_args()

    release = Path(args.release)
    connection = duckdb.connect()
    try:
        artifacts = []
        for name in args.artifacts:
            source = release / name
            if not source.exists():
                raise FileNotFoundError(source)
            stem = source.stem
            target = release / f"{stem}_by_year"
            artifacts.append(partition_one(connection, source, target, overwrite=args.overwrite))
    finally:
        connection.close()
    manifest = {
        "release_id": release.name,
        "layout": "YEAR_PARTITIONED_SIDECAR_V1",
        "artifacts": artifacts,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts) else "FAIL",
    }
    out = release / args.out
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({item["source_artifact"]: {"files": item["file_count"], "rows": item["partition_rows"], "status": item["status"]} for item in artifacts}, sort_keys=True))
    if manifest["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
