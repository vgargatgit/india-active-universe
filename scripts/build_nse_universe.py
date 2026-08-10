from __future__ import annotations

import argparse
import hashlib
from datetime import date
from pathlib import Path

from india_active_universe.identity import apply_manual_overrides, build_identity_rows, load_manual_overrides
from india_active_universe.nse import parse_bhavcopy
from india_active_universe.pipeline import build_active_universe, discover_securities, liquidity_features, validate_observations
from india_active_universe.storage import write_jsonl


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default="data/raw/nse/bhavcopy")
    parser.add_argument("--out", default="data")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--manual-overrides", default="data/reference/manual_identity_overrides.yaml")
    args = parser.parse_args()
    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None
    if start and end and start > end:
        raise SystemExit("--start must be on or before --end")
    observations = []
    findings = []
    paths = []
    for path in sorted(Path(args.raw).glob("*.zip")):
        try:
            point = date.fromisoformat(path.stem)
        except ValueError:
            findings.append({"source_file_id": path.name, "severity": "ERROR", "check": "INVALID_SOURCE_DATE", "security_id": None, "observed_date": None, "message": "Raw filename is not an ISO date"})
            continue
        if (start and point < start) or (end and point > end):
            continue
        paths.append((path, point))
    if not paths:
        raise SystemExit("No valid raw bhavcopy files fall inside the requested date range")
    for path, point in paths:
        try:
            observations.extend(parse_bhavcopy(path.read_bytes(), point, path.name, sha256(path)))
        except Exception as exc:
            findings.append({"source_file_id": path.name, "severity": "ERROR", "check": "SOURCE_PARSE_FAILURE", "message": str(exc)})
    findings.extend({"check": item.check, "severity": item.severity, "source_file_id": item.source_file_id, "security_id": item.security_id, "observed_date": item.observed_date, "message": item.message} for item in validate_observations(observations))
    discovered = discover_securities(observations)
    identities = build_identity_rows(discovered)
    overrides = load_manual_overrides(args.manual_overrides)
    apply_manual_overrides(identities, overrides)
    by_key = {}
    by_symbol = {}
    for row in identities:
        key = (row["exchange"], row["symbol"], row["series"], row.get("candidate_isin") or "")
        by_key.setdefault(key, []).append(row)
        by_symbol.setdefault((row["exchange"], row["symbol"], row["series"]), []).append(row)
    raw_rows = []
    for item in observations:
        applicable = [override for override in overrides if override["exchange"] == item.exchange and override["series"] == item.series and override["symbol"] == item.symbol and override["effective_from"] <= item.date <= override["effective_to"]]
        if len(applicable) > 1:
            candidates = []
        elif applicable:
            candidates = [row for row in identities if row["security_id"] == applicable[0]["security_id"] and row["effective_from"] <= item.date <= row["effective_to"]]
        else:
            exact = by_key.get((item.exchange, item.symbol, item.series, item.isin or ""), [])
            candidates = exact or (by_symbol.get((item.exchange, item.symbol, item.series), []) if not item.isin else [])
        if len(candidates) != 1:
            findings.append({"source_file_id": item.source_file_id, "severity": "ERROR", "check": "IDENTITY_AMBIGUOUS", "security_id": None, "observed_date": item.date.isoformat(), "message": f"No unique identity for {item.exchange}:{item.symbol}:{item.series} with ISIN {item.isin!r}"})
            continue
        identity = candidates[0]
        raw_rows.append({"date": item.date, "security_id": identity["security_id"], "issuer_id": identity["issuer_id"], "listing_episode_id": identity["listing_episode_id"], "symbol_at_date": item.symbol, "isin": item.isin, "company_name": item.company_name, "series": item.series, "instrument_type": identity["instrument_type"], "raw_open": item.open, "raw_high": item.high, "raw_low": item.low, "raw_close": item.close, "volume": item.volume, "traded_value": item.traded_value, "source": item.source_quality, "quality": "OFFICIAL_SOURCE_UNREVIEWED", "source_file_id": item.source_file_id, "source_sha256": item.source_sha256, "parser_version": "nse-bhavcopy-v2", "canonicalization_version": "identity-v1"})
    universe = build_active_universe(raw_rows)
    features = liquidity_features(raw_rows)
    symbol_history = [{"security_id": row["security_id"], "exchange": row["exchange"], "symbol": row["symbol"], "series": row["series"], "effective_from": row["effective_from"], "effective_to": row["effective_to"], "source": row.get("identity_source") or "UNRESOLVED_OBSERVATION", "confidence": row["identity_quality"]} for row in identities]
    root = Path(args.out)
    write_jsonl(root / "canonical/security_master.jsonl", identities, overwrite=True)
    write_jsonl(root / "canonical/symbol_history.jsonl", symbol_history, overwrite=True)
    write_jsonl(root / "canonical/daily_prices_raw.jsonl", raw_rows, overwrite=True)
    write_jsonl(root / "derived/active_universe_daily.jsonl", universe, overwrite=True)
    write_jsonl(root / "derived/liquidity_features.jsonl", features, overwrite=True)
    write_jsonl(root / "derived/data_quality_findings.jsonl", findings, overwrite=True)
    print(f"dates={len(paths)} observations={len(raw_rows)} securities={len(identities)} active_rows={len(universe)} findings={len(findings)}")


if __name__ == "__main__":
    main()
