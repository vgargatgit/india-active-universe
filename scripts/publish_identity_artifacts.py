from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--master", default="data/canonical/security_master.jsonl")
    parser.add_argument("--release", required=True)
    args = parser.parse_args()
    rows = [json.loads(line) for line in Path(args.master).read_text(encoding="utf-8").splitlines() if line]
    issuers = defaultdict(list)
    episodes = defaultdict(list)
    for row in rows:
        issuers[row["issuer_id"]].append(row)
        episodes[row["listing_episode_id"]].append(row)
    issuer_rows = []
    for issuer_id, values in sorted(issuers.items()):
        names = sorted({row.get("company_name") for row in values if row.get("company_name")})
        issuer_rows.append({"issuer_id": issuer_id, "company_names": names, "first_observed_date": min(row["first_seen"] for row in values), "last_observed_date": max(row["last_seen"] for row in values), "identity_quality": "SINGLE_OFFICIAL_SOURCE" if any(row.get("isin") for row in values) else "PARTIAL", "source": "NSE_HISTORICAL_OBSERVATIONS"})
    episode_rows = []
    for episode_id, values in sorted(episodes.items()):
        first = min(values, key=lambda row: row["first_seen"])
        episode_rows.append({"listing_episode_id": episode_id, "security_id": first["security_id"], "exchange": first["exchange"], "start_date": min(row["first_seen"] for row in values), "end_date": max(row["last_seen"] for row in values), "start_reason": "FIRST_OBSERVED_TRADE", "end_reason": "LAST_OBSERVED_TRADE_OR_UNKNOWN", "source": "NSE_HISTORICAL_OBSERVATIONS"})
    release = Path(args.release)
    pq.write_table(pa.Table.from_pylist(issuer_rows), release / "issuer_master.parquet", compression="zstd", use_dictionary=True)
    pq.write_table(pa.Table.from_pylist(episode_rows), release / "listing_episodes.parquet", compression="zstd", use_dictionary=True)
    print(json.dumps({"issuers": len(issuer_rows), "listing_episodes": len(episode_rows)}, sort_keys=True))


if __name__ == "__main__":
    main()
