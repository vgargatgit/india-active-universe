from __future__ import annotations

import hashlib
from datetime import date
from typing import Any, Iterable

from .models import IdentityQuality


def stable_id(prefix: str, *parts: str) -> str:
    payload = "|".join(part.strip().upper() for part in parts)
    return f"{prefix}_{hashlib.sha256(payload.encode()).hexdigest()[:16]}"


def build_identity_rows(discovered: Iterable[dict[str, Any]], *, canonicalization_version: str = "identity-v1") -> list[dict[str, Any]]:
    """Create conservative provisional identities from observed exchange keys.

    Provisional IDs are stable for the observed listing episode but remain PARTIAL
    until official evidence or a reviewed override supplies stronger identity.
    """
    output = []
    for row in discovered:
        exchange, symbol, series = row["exchange"], row["symbol"], row["series"]
        identity_basis = row.get("candidate_isin")
        episode = stable_id("EP", exchange, identity_basis or symbol, series)
        security = stable_id("SEC", exchange, identity_basis or symbol, series)
        issuer = stable_id("ISSUER", exchange, identity_basis or row.get("company_name") or symbol)
        quality = IdentityQuality.SINGLE_OFFICIAL_SOURCE.value if identity_basis else IdentityQuality.PARTIAL.value
        output.append({**row, "isin": identity_basis, "issuer_id": issuer, "security_id": security, "listing_episode_id": episode, "effective_from": row["first_seen"], "effective_to": row["last_seen"], "identity_quality": quality, "identity_source": "NSE_OFFICIAL_BHAVCOPY_ISIN" if identity_basis else None, "review_status": "REVIEW_REQUIRED" if not identity_basis else "UNREVIEWED", "canonicalization_version": canonicalization_version})
    return output


def resolve_symbol(rows: Iterable[dict[str, Any]], symbol: str, as_of: date, *, exchange: str = "NSE", series: str = "EQ") -> dict[str, Any]:
    matches = [row for row in rows if row.get("exchange") == exchange and row.get("series") == series and row.get("symbol") == symbol and row["effective_from"] <= as_of and (row.get("effective_to") is None or as_of <= row["effective_to"])]
    if len(matches) != 1:
        raise LookupError(f"Ambiguous or missing dated identity: {exchange}:{symbol}:{series}:{as_of}")
    return matches[0]
