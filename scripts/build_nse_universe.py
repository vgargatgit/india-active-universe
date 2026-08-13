from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from datetime import date
from pathlib import Path

from india_active_universe.identity import apply_manual_overrides, build_identity_rows, load_manual_overrides
from india_active_universe.nse import parse_bhavcopy
from india_active_universe.pipeline import build_active_snapshot, discover_securities, validate_observations
from india_active_universe.profiles import PARSER_VERSIONS
from india_active_universe.storage import _encode, write_jsonl


IDENTITY_SERIES = "EQ"
RAW_EXECUTION_SERIES_ALIASES = {"BE": IDENTITY_SERIES}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def selected_paths(raw: Path, start: date | None, end: date | None, findings: list[dict]) -> list[tuple[Path, date]]:
    paths = []
    for path in sorted(raw.glob("*.zip")):
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
    return paths


def parse_daily(path: Path, point: date, findings: list[dict], *, validate: bool) -> list:
    try:
        items = list(parse_bhavcopy(path.read_bytes(), point, path.name, sha256(path)))
    except Exception as exc:
        findings.append({"source_file_id": path.name, "severity": "ERROR", "check": "SOURCE_PARSE_FAILURE", "security_id": None, "observed_date": point.isoformat(), "message": str(exc)})
        return []
    if validate:
        findings.extend({"check": item.check, "severity": item.severity, "source_file_id": item.source_file_id, "security_id": item.security_id, "observed_date": item.observed_date, "message": item.message} for item in validate_observations(items))
    return items


def identity_observation(item):
    """Use BE observations as identity continuity evidence without changing the source raw series."""
    alias = RAW_EXECUTION_SERIES_ALIASES.get(item.series)
    return replace(item, series=alias) if alias else item


def write_row(handle, row: dict) -> None:
    handle.write(json.dumps(_encode(row), sort_keys=True, separators=(",", ":")) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default="data/raw/nse/bhavcopy")
    parser.add_argument("--out", default="data")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--manual-overrides", default="data/reference/manual_identity_overrides.yaml")
    parser.add_argument("--canonicalization-version", default="identity-v2")
    args = parser.parse_args()
    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None
    if start and end and start > end:
        raise SystemExit("--start must be on or before --end")

    findings: list[dict] = []
    paths = selected_paths(Path(args.raw), start, end, findings)
    session_index_by_date = {point: index for index, (_path, point) in enumerate(paths, start=1)}

    def observations():
        for path, point in paths:
            for item in parse_daily(path, point, findings, validate=True):
                yield item

    discovered = discover_securities(identity_observation(item) for item in observations())
    v1_identities = build_identity_rows(discovered, canonicalization_version="identity-v1")
    identities = build_identity_rows(discovered, canonicalization_version=args.canonicalization_version, session_index_by_date=session_index_by_date)
    overrides = load_manual_overrides(args.manual_overrides)
    apply_manual_overrides(identities, overrides)
    by_key: dict[tuple, list[dict]] = {}
    by_symbol: dict[tuple, list[dict]] = {}
    for row in identities:
        by_key.setdefault((row["exchange"], row["symbol"], row["series"], row.get("candidate_isin") or ""), []).append(row)
        by_symbol.setdefault((row["exchange"], row["symbol"], row["series"]), []).append(row)

    root = Path(args.out)
    canonical, derived = root / "canonical", root / "derived"
    canonical.mkdir(parents=True, exist_ok=True)
    derived.mkdir(parents=True, exist_ok=True)
    raw_path = canonical / "daily_prices_raw.jsonl"
    active_path = derived / "active_universe_daily.jsonl"
    unresolved_path = canonical / "unresolved_observed_trading.jsonl"
    raw_handle = raw_path.open("w", encoding="utf-8")
    active_handle = active_path.open("w", encoding="utf-8")
    unresolved_handle = unresolved_path.open("w", encoding="utf-8")
    raw_count = active_count = unresolved_count = 0
    try:
        for path, point in paths:
            day_rows = []
            for item in parse_daily(path, point, findings, validate=False):
                identity_series = RAW_EXECUTION_SERIES_ALIASES.get(item.series, item.series)
                applicable = [override for override in overrides if override["exchange"] == item.exchange and override["series"] == identity_series and override["symbol"] == item.symbol and override["effective_from"] <= item.date <= override["effective_to"]]
                if len(applicable) > 1:
                    candidates = []
                elif applicable:
                    candidates = [row for row in identities if row["security_id"] == applicable[0]["security_id"] and row["effective_from"] <= item.date <= row["effective_to"]]
                else:
                    exact = by_key.get((item.exchange, item.symbol, identity_series, item.isin or ""), [])
                    candidates = exact or (by_symbol.get((item.exchange, item.symbol, identity_series), []) if not item.isin else [])
                if len(candidates) != 1:
                    findings.append({"source_file_id": item.source_file_id, "severity": "ERROR", "check": "IDENTITY_AMBIGUOUS", "security_id": None, "observed_date": item.date.isoformat(), "message": f"No unique identity for {item.exchange}:{item.symbol}:{item.series} with ISIN {item.isin!r}"})
                    write_row(unresolved_handle, {"date": item.date, "exchange": item.exchange, "symbol": item.symbol, "series": item.series, "isin": item.isin, "company_name": item.company_name, "raw_open": item.open, "raw_high": item.high, "raw_low": item.low, "raw_close": item.close, "volume": item.volume, "traded_value": item.traded_value, "source_file_id": item.source_file_id, "source_sha256": item.source_sha256, "source_quality": item.source_quality, "resolution_status": "UNRESOLVED", "candidate_security_ids": [row["security_id"] for row in candidates]})
                    unresolved_count += 1
                    continue
                identity = candidates[0]
                row = {"date": item.date, "security_id": identity["security_id"], "issuer_id": identity["issuer_id"], "listing_episode_id": identity["listing_episode_id"], "symbol_at_date": item.symbol, "isin": item.isin, "company_name": item.company_name, "series": item.series, "instrument_type": identity["instrument_type"], "instrument_type_quality": identity.get("instrument_type_quality"), "instrument_type_source": identity.get("instrument_type_source"), "raw_open": item.open, "raw_high": item.high, "raw_low": item.low, "raw_close": item.close, "volume": item.volume, "traded_value": item.traded_value, "source": item.source_quality, "quality": "OFFICIAL_SOURCE_UNREVIEWED", "source_file_id": item.source_file_id, "source_sha256": item.source_sha256, "parser_version": PARSER_VERSIONS["nse_bhavcopy"], "canonicalization_version": args.canonicalization_version}
                day_rows.append(row)
                write_row(raw_handle, row)
                raw_count += 1
            for row in build_active_snapshot(day_rows, point):
                write_row(active_handle, row)
                active_count += 1
    finally:
        raw_handle.close()
        active_handle.close()
        unresolved_handle.close()

    symbol_history = [{"security_id": row["security_id"], "exchange": row["exchange"], "symbol": row["symbol"], "series": row["series"], "effective_from": row["effective_from"], "effective_to": row["effective_to"], "source": row.get("identity_source") or "UNRESOLVED_OBSERVATION", "confidence": row["identity_quality"]} for row in identities]
    v1_by_source_key = {
        (row["exchange"], row["symbol"], row["series"], row.get("candidate_isin") or "", row["effective_from"], row["effective_to"]): row
        for row in v1_identities
    }
    migration_rows = []
    for row in identities:
        source_key = (row["exchange"], row["symbol"], row["series"], row.get("candidate_isin") or "", row["effective_from"], row["effective_to"])
        old = v1_by_source_key.get(source_key)
        if not old:
            continue
        reason = "UNCHANGED"
        quality = "UNCHANGED"
        evidence = "IDENTITY_V1_COMPATIBLE"
        if old["security_id"] != row["security_id"]:
            reason = "ADJACENT_SOURCE_IDENTITY_CONTINUITY"
            quality = "RECONSTRUCTED_PRE_ISIN_CONTINUITY" if row.get("identity_source") == "RECONSTRUCTED_PRE_ISIN_CONTINUITY" else "RECONSTRUCTED_ADJACENT_SYMBOL_ISIN_CONTINUITY"
            evidence = "same exchange/symbol/series; adjacent official-session observations; effective-dated source ISIN preserved"
        migration_rows.append({
            "old_security_id": old["security_id"],
            "new_security_id": row["security_id"],
            "old_listing_episode_id": old["listing_episode_id"],
            "new_listing_episode_id": row["listing_episode_id"],
            "exchange": row["exchange"],
            "symbol": row["symbol"],
            "series": row["series"],
            "source_isin": row.get("isin"),
            "effective_from": row["effective_from"],
            "effective_to": row["effective_to"],
            "migration_reason": reason,
            "identity_evidence": evidence,
            "migration_quality": quality,
            "canonicalization_from": "identity-v1",
            "canonicalization_to": args.canonicalization_version,
        })
    write_jsonl(canonical / "security_master.jsonl", identities, overwrite=True)
    write_jsonl(canonical / "symbol_history.jsonl", symbol_history, overwrite=True)
    write_jsonl(canonical / "security_id_migration.jsonl", migration_rows, overwrite=True)
    write_jsonl(derived / "liquidity_features.jsonl", [], overwrite=True)
    write_jsonl(derived / "data_quality_findings.jsonl", findings, overwrite=True)
    print(f"dates={len(paths)} observations={raw_count} unresolved_observations={unresolved_count} securities={len(identities)} active_rows={active_count} findings={len(findings)}")


if __name__ == "__main__":
    main()
