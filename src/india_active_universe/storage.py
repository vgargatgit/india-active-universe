from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable


def _encode(value: Any) -> Any:
    if isinstance(value, (date, Decimal)):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(item) for item in value]
    return value


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]], *, overwrite: bool = False) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not overwrite:
        raise FileExistsError(f"Immutable artifact already exists: {output}")
    with output.open("x" if not overwrite else "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(_encode(row), sort_keys=True, separators=(",", ":")) + "\n")


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def iter_jsonl(path: str | Path):
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def write_table(path: str | Path, rows: Iterable[dict[str, Any]], *, overwrite: bool = False) -> None:
    """Write Parquet when pyarrow is installed, otherwise use explicit JSONL."""
    output = Path(path)
    materialized = list(rows)
    if output.suffix == ".parquet":
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise RuntimeError("Parquet output requires the optional 'data' dependencies") from exc
        if output.exists() and not overwrite:
            raise FileExistsError(f"Immutable artifact already exists: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pylist([_encode(row) for row in materialized]), output)
        return
    write_jsonl(output, materialized, overwrite=overwrite)
