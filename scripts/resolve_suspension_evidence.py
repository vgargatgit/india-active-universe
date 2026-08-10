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

    master = pq.read_table(args.master).to_pylist()
    by_name: dict[str, list[dict]] = defaultdict(list)
    for row in master:
        name = clean(row.get("company_name"))
        if name:
            by_name[name].append(row)

    output = []
    counts = defaultdict(int)
    for row in pq.read_table(args.evidence).to_pylist():
        point = row.get("effective_date") or row.get("published_date")
        candidates = {}
        for name in row.get("historical_company_names") or []:
            for candidate in by_name.get(clean(name), []):
                if point and candidate["first_seen"] <= point <= candidate["last_seen"]:
                    candidates[candidate["security_id"]] = candidate
        if len(candidates) == 1:
            candidate = next(iter(candidates.values()))
            quality = "EXACT_COMPANY_DATE_MATCH"
            counts[quality] += 1
            linked = {"security_id": candidate["security_id"], "issuer_id": candidate.get("issuer_id"), "listing_episode_id": candidate.get("listing_episode_id")}
        elif candidates:
            quality = "AMBIGUOUS_COMPANY_DATE_MATCH"
            counts[quality] += 1
            linked = {"security_id": None, "issuer_id": None, "listing_episode_id": None}
        else:
            quality = "IDENTITY_REVIEW_REQUIRED"
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
