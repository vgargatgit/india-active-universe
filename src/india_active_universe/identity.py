from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from .models import IdentityQuality


def stable_id(prefix: str, *parts: str) -> str:
    payload = "|".join(part.strip().upper() for part in parts)
    return f"{prefix}_{hashlib.sha256(payload.encode()).hexdigest()[:16]}"


def continuity_chains(
    discovered_rows: list[dict[str, Any]],
    *,
    session_index_by_date: dict[date, int] | None = None,
    max_gap_sessions: int = 1,
) -> dict[int, int]:
    """Map discovered-row positions to conservative same-symbol continuity chains."""
    chain_by_index: dict[int, int] = {}
    parent: dict[int, int] = {}

    def find(value: int) -> int:
        parent.setdefault(value, value)
        if parent[value] != value:
            parent[value] = find(parent[value])
        return parent[value]

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    def adjacent(previous_last: date, current_first: date) -> bool:
        if current_first <= previous_last:
            return False
        if session_index_by_date:
            previous_session = session_index_by_date.get(previous_last)
            current_session = session_index_by_date.get(current_first)
            return (
                previous_session is not None
                and current_session is not None
                and 0 < current_session - previous_session <= max_gap_sessions
            )
        return 0 < (current_first - previous_last).days <= 7

    grouped: dict[tuple[str, str, str], list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for index, row in enumerate(discovered_rows):
        grouped[(row["exchange"], row["symbol"], row["series"])].append((index, row))
    next_chain = 0
    for values in grouped.values():
        values.sort(key=lambda item: (item[1]["first_seen"], item[1]["last_seen"], item[1].get("candidate_isin") or ""))
        previous_row: dict[str, Any] | None = None
        current_chain: int | None = None
        for index, row in values:
            join_previous = False
            if previous_row is not None and current_chain is not None:
                join_previous = adjacent(previous_row["last_seen"], row["first_seen"])
            if not join_previous:
                current_chain = next_chain
                next_chain += 1
            chain_by_index[index] = current_chain
            parent.setdefault(current_chain, current_chain)
            previous_row = row
    isin_grouped: dict[tuple[str, str, str], list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for index, row in enumerate(discovered_rows):
        isin = row.get("candidate_isin")
        if isin:
            isin_grouped[(row["exchange"], row["series"], str(isin).upper())].append((index, row))
    for values in isin_grouped.values():
        values.sort(key=lambda item: (item[1]["first_seen"], item[1]["last_seen"], item[1]["symbol"]))
        previous_index: int | None = None
        previous_row: dict[str, Any] | None = None
        for index, row in values:
            if previous_index is not None and previous_row is not None and adjacent(previous_row["last_seen"], row["first_seen"]):
                union(chain_by_index[previous_index], chain_by_index[index])
            previous_index = index
            previous_row = row
    root_map: dict[int, int] = {}
    for chain in sorted(set(chain_by_index.values())):
        root = find(chain)
        root_map.setdefault(root, len(root_map))
    for index, chain in list(chain_by_index.items()):
        chain_by_index[index] = root_map[find(chain)]
    return chain_by_index


def build_identity_rows(
    discovered: Iterable[dict[str, Any]],
    *,
    canonicalization_version: str = "identity-v1",
    session_index_by_date: dict[date, int] | None = None,
) -> list[dict[str, Any]]:
    """Create conservative provisional identities from observed exchange keys.

    Provisional IDs are stable for the observed listing episode but remain PARTIAL
    until official evidence or a reviewed override supplies stronger identity.
    """
    discovered_rows = list(discovered)
    source_start = min((row["first_seen"] for row in discovered_rows), default=None)
    output = []
    chain_by_index = continuity_chains(discovered_rows, session_index_by_date=session_index_by_date) if canonicalization_version != "identity-v1" else {index: index for index, _row in enumerate(discovered_rows)}
    rows_by_chain: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for index, row in enumerate(discovered_rows):
        rows_by_chain[chain_by_index[index]].append(row)
    chain_identity: dict[int, dict[str, str | bool | None]] = {}
    for chain, values in rows_by_chain.items():
        values.sort(key=lambda item: (item["first_seen"], item["last_seen"], item.get("candidate_isin") or ""))
        first = values[0]
        first_isin = next((item.get("candidate_isin") for item in values if item.get("candidate_isin")), None)
        canonical_basis = first_isin or first["symbol"]
        has_pre_isin = any(not item.get("candidate_isin") for item in values)
        has_isin = any(item.get("candidate_isin") for item in values)
        reconstructed = canonicalization_version != "identity-v1" and len(values) > 1
        chain_identity[chain] = {
            "security_id": stable_id("SEC", first["exchange"], canonical_basis, first["series"]),
            "listing_episode_id": stable_id("EP", first["exchange"], canonical_basis, first["series"]),
            "issuer_id": stable_id("ISSUER", first["exchange"], canonical_basis or first.get("company_name") or first["symbol"]),
            "reconstructed": reconstructed,
            "has_pre_isin": has_pre_isin,
            "has_isin": has_isin,
        }
    for index, row in enumerate(discovered_rows):
        exchange, symbol, series = row["exchange"], row["symbol"], row["series"]
        identity_basis = row.get("candidate_isin")
        chain = chain_identity[chain_by_index[index]]
        episode = str(chain["listing_episode_id"])
        security = str(chain["security_id"])
        issuer = str(chain["issuer_id"])
        if chain["reconstructed"]:
            quality = IdentityQuality.RECONSTRUCTED_HIGH_CONFIDENCE.value
        else:
            quality = IdentityQuality.SINGLE_OFFICIAL_SOURCE.value if identity_basis else IdentityQuality.PARTIAL.value
        if chain["reconstructed"] and chain["has_pre_isin"] and chain["has_isin"]:
            identity_source = "RECONSTRUCTED_PRE_ISIN_CONTINUITY"
        elif chain["reconstructed"]:
            identity_source = "RECONSTRUCTED_ADJACENT_SYMBOL_ISIN_CONTINUITY"
        else:
            identity_source = "NSE_OFFICIAL_BHAVCOPY_ISIN" if identity_basis else None
        instrument_quality = "HEURISTIC_HIGH_CONFIDENCE" if row.get("instrument_type") == "ORDINARY_EQUITY" else "EXPLICIT_EXCHANGE_MARKER"
        left_censored = bool(source_start and row["first_seen"] == source_start)
        listing_age_quality = "LISTING_HISTORY_LEFT_CENSORED" if left_censored else "FIRST_OBSERVED_TRADE_DATE"
        output.append({**row, "isin": identity_basis, "issuer_id": issuer, "security_id": security, "listing_episode_id": episode, "effective_from": row["first_seen"], "effective_to": row["last_seen"], "known_listing_date": None, "listing_date_quality": "UNKNOWN_LEFT_CENSORED" if left_censored else "UNKNOWN_FIRST_OBSERVED", "observed_history_start": row["first_seen"], "listing_age_sessions_quality": listing_age_quality, "listing_history_left_censored": left_censored, "identity_quality": quality, "identity_source": identity_source, "instrument_type_quality": instrument_quality, "instrument_type_source": "NSE_EQ_SERIES_AND_HISTORICAL_SYMBOL_COMPANY_MARKER", "review_status": "REVIEW_REQUIRED" if not identity_basis and not chain["reconstructed"] else "UNREVIEWED", "canonicalization_version": canonicalization_version})
    return output


def load_manual_overrides(path: str | Path) -> list[dict[str, Any]]:
    """Load only approved, non-overlapping, evidence-backed overrides."""
    source = Path(path)
    if not source.exists():
        return []
    try:
        import yaml
    except ImportError as exc:
        text = source.read_text(encoding="utf-8")
        active_lines = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
        if active_lines == [] or active_lines == ["overrides: []"]:
            return []
        raise RuntimeError("PyYAML is required for non-empty manual identity overrides") from exc
    payload = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    overrides = payload.get("overrides")
    if not isinstance(overrides, list):
        raise ValueError("manual identity overrides must contain an overrides list")
    output = []
    ranges: list[tuple[str, str, str, date, date]] = []
    required = {"exchange", "symbol", "series", "effective_from", "effective_to", "security_id", "evidence_references", "rationale", "review_status"}
    for index, override in enumerate(overrides):
        if not isinstance(override, dict) or required - set(override):
            raise ValueError(f"manual override {index} is missing required fields")
        if override["exchange"] != "NSE" or override["series"] != "EQ" or not str(override["symbol"]).strip():
            raise ValueError(f"manual override {index} must target a non-empty NSE EQ symbol")
        start = date.fromisoformat(str(override["effective_from"]))
        end = date.fromisoformat(str(override["effective_to"]))
        if end < start or override["review_status"] != "APPROVED":
            raise ValueError(f"manual override {index} has an invalid range or review status")
        if not isinstance(override["evidence_references"], list) or not override["evidence_references"] or not str(override["rationale"]).strip():
            raise ValueError(f"manual override {index} needs evidence references and rationale")
        key = (override["exchange"], str(override["symbol"]).upper(), override["series"])
        for old_exchange, old_symbol, old_series, old_start, old_end in ranges:
            if key == (old_exchange, old_symbol, old_series) and start <= old_end and old_start <= end:
                raise ValueError(f"overlapping manual override range for {key}")
        ranges.append((*key, start, end))
        output.append({**override, "symbol": key[1], "effective_from": start, "effective_to": end})
    return output


def apply_manual_overrides(identities: list[dict[str, Any]], overrides: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return compact dated overrides and annotate the affected canonical rows."""
    applied = []
    for override in overrides:
        matching = [row for row in identities if row["security_id"] == override["security_id"]]
        if not matching:
            raise ValueError(f"manual override references unknown security_id {override['security_id']}")
        if any(row["exchange"] != override["exchange"] or row["series"] != override["series"] for row in matching):
            raise ValueError(f"manual override security does not match exchange or series: {override['security_id']}")
        if not any(row["effective_to"] >= override["effective_from"] and override["effective_to"] >= row["effective_from"] for row in matching):
            raise ValueError(f"manual override does not overlap security history: {override['security_id']}")
        replacement = []
        for row in identities:
            if row["security_id"] != override["security_id"]:
                replacement.append(row)
                continue
            row_start = row["effective_from"]
            row_end = row["effective_to"] or override["effective_to"]
            overlap_start = max(row_start, override["effective_from"])
            overlap_end = min(row_end, override["effective_to"])
            if overlap_start > overlap_end:
                replacement.append(row)
                continue
            if row_start < overlap_start:
                before = dict(row)
                before["effective_to"] = date.fromordinal(overlap_start.toordinal() - 1)
                replacement.append(before)
            reviewed = dict(row)
            reviewed.update({
                "symbol": override["symbol"],
                "effective_from": overlap_start,
                "effective_to": overlap_end,
                "identity_quality": IdentityQuality.MULTI_SOURCE_VERIFIED.value,
                "identity_source": "MANUAL_APPROVED_OVERRIDE",
                "review_status": "APPROVED",
                "source_reference": ";".join(str(item) for item in override["evidence_references"]),
                "notes": str(override["rationale"]),
            })
            replacement.append(reviewed)
            if row_end > overlap_end:
                after = dict(row)
                after["effective_from"] = date.fromordinal(overlap_end.toordinal() + 1)
                replacement.append(after)
        identities[:] = sorted(replacement, key=lambda row: (row["security_id"], row["effective_from"], row.get("symbol", "")))
        applied.append(override)
    return applied


def resolve_symbol(rows: Iterable[dict[str, Any]], symbol: str, as_of: date, *, exchange: str = "NSE", series: str = "EQ") -> dict[str, Any]:
    matches = [row for row in rows if row.get("exchange") == exchange and row.get("series") == series and row.get("symbol") == symbol and row["effective_from"] <= as_of and (row.get("effective_to") is None or as_of <= row["effective_to"])]
    if len(matches) != 1:
        raise LookupError(f"Ambiguous or missing dated identity: {exchange}:{symbol}:{series}:{as_of}")
    return matches[0]
