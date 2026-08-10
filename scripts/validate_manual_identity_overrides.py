#!/usr/bin/env python3
"""Validate evidence-backed manual identity overrides before canonical use."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - environment dependency
    yaml = None


REQUIRED = {
    "exchange", "symbol", "series", "effective_from", "effective_to",
    "security_id", "evidence_references", "rationale", "review_status",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/reference/manual_identity_overrides.yaml")
    args = parser.parse_args()
    source = Path(args.input).read_text(encoding="utf-8")
    if yaml is None:
        active_lines = [line.strip() for line in source.splitlines() if line.strip() and not line.lstrip().startswith("#")]
        if active_lines == ["overrides: []"]:
            print("VALID_OVERRIDES 0")
            return
        raise SystemExit("PyYAML is required to validate non-empty manual identity overrides")
    payload = yaml.safe_load(source) or {}
    overrides = payload.get("overrides")
    if not isinstance(overrides, list):
        raise SystemExit("overrides must be a list")

    ranges: list[tuple[str, str, str, date, date, str]] = []
    for index, override in enumerate(overrides):
        if not isinstance(override, dict) or REQUIRED - set(override):
            missing = sorted(REQUIRED - set(override or {}))
            raise SystemExit(f"override[{index}] missing fields: {missing}")
        if override["exchange"] != "NSE" or not override["symbol"] or override["series"] != "EQ":
            raise SystemExit(f"override[{index}] must target NSE EQ with a symbol")
        start = date.fromisoformat(str(override["effective_from"]))
        end = date.fromisoformat(str(override["effective_to"]))
        if end < start:
            raise SystemExit(f"override[{index}] has reversed effective dates")
        if override["review_status"] != "APPROVED":
            raise SystemExit(f"override[{index}] is not APPROVED")
        if not isinstance(override["evidence_references"], list) or not override["evidence_references"]:
            raise SystemExit(f"override[{index}] needs evidence_references")
        if not str(override["rationale"]).strip():
            raise SystemExit(f"override[{index}] needs rationale")
        key = (override["exchange"], override["symbol"], override["series"])
        for old_exchange, old_symbol, old_series, old_start, old_end, old_security in ranges:
            if key == (old_exchange, old_symbol, old_series) and start <= old_end and old_start <= end:
                raise SystemExit(f"overlapping override ranges for {key}: {old_security} and {override['security_id']}")
        ranges.append((*key, start, end, str(override["security_id"])))
    print(f"VALID_OVERRIDES {len(overrides)}")


if __name__ == "__main__":
    main()
