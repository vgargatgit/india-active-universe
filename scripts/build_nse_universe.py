from __future__ import annotations

import argparse
import hashlib
from datetime import date
from pathlib import Path

from india_active_universe.identity import build_identity_rows
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
    args = parser.parse_args()
    observations = []
    findings = []
    for path in sorted(Path(args.raw).glob("*.zip")):
        try:
            point = date.fromisoformat(path.stem)
            observations.extend(parse_bhavcopy(path.read_bytes(), point, path.name, sha256(path)))
        except Exception as exc:
            findings.append({"source_file_id": path.name, "severity": "ERROR", "check": "SOURCE_PARSE_FAILURE", "message": str(exc)})
    findings.extend({"check": item.check, "severity": item.severity, "source_file_id": item.source_file_id, "security_id": item.security_id, "observed_date": item.observed_date, "message": item.message} for item in validate_observations(observations))
    discovered = discover_securities(observations)
    identities = build_identity_rows(discovered)
    by_key = {(row["exchange"], row["symbol"], row["series"]): row for row in identities}
    raw_rows = []
    for item in observations:
        identity = by_key[(item.exchange, item.symbol, item.series)]
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
    print(f"observations={len(raw_rows)} securities={len(identities)} active_rows={len(universe)} findings={len(findings)}")


if __name__ == "__main__":
    main()
