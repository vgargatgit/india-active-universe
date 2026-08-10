from __future__ import annotations

import argparse
from pathlib import Path

from india_active_universe.pipeline import liquidity_features
from india_active_universe.storage import read_jsonl, write_jsonl


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prices", default="data/canonical/daily_prices_raw.jsonl")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    rows = read_jsonl(args.prices)
    output = liquidity_features(rows)
    write_jsonl(Path(args.out), output, overwrite=True)
    print(f"features={len(output)} securities={len({row['security_id'] for row in output})}")


if __name__ == "__main__":
    main()
