#!/usr/bin/env python3
"""Validate holder-value continuity around official price-action events."""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq


SCHEMA = pa.schema([
    pa.field("event_id", pa.string()),
    pa.field("security_id", pa.string()),
    pa.field("event_type", pa.string()),
    pa.field("ex_date", pa.string()),
    pa.field("price_factor", pa.float64()),
    pa.field("share_factor", pa.float64()),
    pa.field("pre_event_date", pa.string()),
    pa.field("pre_event_close", pa.float64()),
    pa.field("post_event_date", pa.string()),
    pa.field("post_event_close", pa.float64()),
    pa.field("holder_value_ratio", pa.float64()),
    pa.field("validation_status", pa.string()),
    pa.field("boundary_price_factor", pa.float64()),
    pa.field("boundary_share_factor", pa.float64()),
    pa.field("boundary_event_count", pa.int64()),
    pa.field("boundary_event_ids", pa.string()),
])


def classify_boundary(pre_close: float | None, post_close: float | None, share_factor: float, warning_threshold: float) -> tuple[float | None, str]:
    """Return holder-value ratio and an explicit boundary status."""
    if pre_close is None and post_close is None:
        return None, "NO_BOUNDARY_OBSERVATIONS"
    if pre_close is None:
        return None, "NO_PRE_EVENT_OBSERVATION"
    if post_close is None:
        return None, "NO_POST_EVENT_OBSERVATION"
    if pre_close <= 0:
        return None, "INVALID_PRE_EVENT_PRICE"
    ratio = float(post_close * share_factor / pre_close)
    status = "PASS" if abs(ratio - 1.0) <= warning_threshold else "WARNING_LARGE_BOUNDARY_MOVE"
    return ratio, status


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", required=True)
    parser.add_argument("--prices", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--warning-threshold", type=float, default=0.15)
    args = parser.parse_args()

    con = duckdb.connect()
    query = """
        WITH events AS (
            SELECT event_id, security_id, event_type, coalesce(ex_date, event_date) AS ex_date,
                   price_factor, share_factor
            FROM read_parquet(?)
            WHERE security_id IS NOT NULL
              AND event_type IN ('SPLIT', 'REVERSE_SPLIT', 'BONUS')
              AND price_factor IS NOT NULL
              AND share_factor IS NOT NULL
              AND coalesce(ex_date, event_date) IS NOT NULL
        )
        , event_groups AS (
            SELECT security_id, ex_date,
                   exp(sum(ln(price_factor))) AS boundary_price_factor,
                   exp(sum(ln(share_factor))) AS boundary_share_factor,
                   count(*) AS boundary_event_count,
                   string_agg(event_id, ', ' ORDER BY event_id) AS boundary_event_ids
            FROM events
            GROUP BY security_id, ex_date
        )
        SELECT e.event_id, e.security_id, e.event_type, e.ex_date,
               e.price_factor, e.share_factor,
               max_by(p.date, p.date) FILTER (WHERE p.date < e.ex_date) AS pre_event_date,
               max_by(p.raw_close, p.date) FILTER (WHERE p.date < e.ex_date) AS pre_event_close,
               min_by(p.date, p.date) FILTER (WHERE p.date >= e.ex_date) AS post_event_date,
               min_by(p.raw_close, p.date) FILTER (WHERE p.date >= e.ex_date) AS post_event_close,
               g.boundary_price_factor, g.boundary_share_factor, g.boundary_event_count, g.boundary_event_ids
        FROM events e
        JOIN event_groups g USING (security_id, ex_date)
        LEFT JOIN read_parquet(?) p ON p.security_id = e.security_id
        GROUP BY e.event_id, e.security_id, e.event_type, e.ex_date, e.price_factor, e.share_factor,
                 g.boundary_price_factor, g.boundary_share_factor, g.boundary_event_count, g.boundary_event_ids
    """
    raw = con.execute(query, [args.events, args.prices]).fetchall()
    rows = []
    for event_id, security_id, event_type, ex_date, price_factor, share_factor, pre_date, pre_close, post_date, post_close, boundary_price_factor, boundary_share_factor, boundary_event_count, boundary_event_ids in raw:
        ratio, status = classify_boundary(pre_close, post_close, boundary_share_factor, args.warning_threshold)
        rows.append({
            "event_id": event_id, "security_id": security_id, "event_type": event_type, "ex_date": ex_date,
            "price_factor": price_factor, "share_factor": share_factor,
            "pre_event_date": pre_date, "pre_event_close": pre_close,
            "post_event_date": post_date, "post_event_close": post_close,
            "holder_value_ratio": ratio, "validation_status": status,
            "boundary_price_factor": boundary_price_factor, "boundary_share_factor": boundary_share_factor,
            "boundary_event_count": boundary_event_count, "boundary_event_ids": boundary_event_ids,
        })
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA), path, compression="zstd")
    counts = {}
    for row in rows:
        counts[row["validation_status"]] = counts.get(row["validation_status"], 0) + 1
    print(f"events={len(rows)} statuses={counts}")


if __name__ == "__main__":
    main()
