from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def clean(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--master", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    output = []
    counts = defaultdict(int)
    for row in pq.read_table(args.evidence).to_pylist():
        # A source page can contain several press releases. Candidate names are
        # evidence only; page-level matching must not become canonical identity.
        quality = "PAGE_LEVEL_IDENTITY_REVIEW_REQUIRED"
        counts[quality] += 1
        linked = {"security_id": None, "issuer_id": None, "listing_episode_id": None}
        output.append({**row, **linked, "identity_match_quality": quality})

    fields = list(pq.read_schema(args.evidence))
    fields.extend([pa.field("security_id", pa.string()), pa.field("issuer_id", pa.string()), pa.field("listing_episode_id", pa.string()), pa.field("identity_match_quality", pa.string())])
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(output, schema=pa.schema(fields)), target, compression="zstd", use_dictionary=True)
    print(dict(sorted(counts.items())))


if __name__ == "__main__":
    main()
