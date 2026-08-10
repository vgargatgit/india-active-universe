from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any


class IdentityQuality(str, Enum):
    OFFICIAL_EXCHANGE_IDENTITY = "OFFICIAL_EXCHANGE_IDENTITY"
    MULTI_SOURCE_VERIFIED = "MULTI_SOURCE_VERIFIED"
    RECONSTRUCTED_HIGH_CONFIDENCE = "RECONSTRUCTED_HIGH_CONFIDENCE"
    SINGLE_OFFICIAL_SOURCE = "SINGLE_OFFICIAL_SOURCE"
    PARTIAL = "PARTIAL"
    UNRESOLVED = "UNRESOLVED"
    MODEL_CANDIDATE_ONLY = "MODEL_CANDIDATE_ONLY"


class TradingStatus(str, Enum):
    ACTIVE_TRADING = "ACTIVE_TRADING"
    SUSPENDED = "SUSPENDED"
    DELISTED = "DELISTED"
    UNKNOWN_STATUS = "UNKNOWN_STATUS"


class InstrumentType(str, Enum):
    ORDINARY_EQUITY = "ORDINARY_EQUITY"
    ETF = "ETF"
    MUTUAL_FUND = "MUTUAL_FUND"
    PREFERENCE_SHARE = "PREFERENCE_SHARE"
    WARRANT = "WARRANT"
    BOND = "BOND"
    REIT = "REIT"
    INVIT = "INVIT"
    SME = "SME"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Security:
    security_id: str
    issuer_id: str
    listing_episode_id: str
    exchange: str
    instrument_type: InstrumentType
    series: str
    symbol: str
    isin: str | None
    company_name: str | None
    effective_from: date
    effective_to: date | None = None
    listing_date: date | None = None
    delisting_date: date | None = None
    first_observed_trade_date: date | None = None
    last_observed_trade_date: date | None = None
    identity_quality: IdentityQuality = IdentityQuality.UNRESOLVED
    identity_source: str | None = None
    source_reference: str | None = None
    source_sha256: str | None = None
    review_status: str = "UNREVIEWED"
    notes: str | None = None


@dataclass(frozen=True)
class DailyObservation:
    date: date
    exchange: str
    symbol: str
    series: str
    security_id: str | None
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    volume: int | None
    traded_value: Decimal | None
    source_file_id: str
    source_sha256: str
    source_quality: str
    isin: str | None = None
    company_name: str | None = None


def as_record(value: Any) -> dict[str, Any]:
    """Serialize dataclasses/enums for stable JSON/row-oriented consumers."""
    if hasattr(value, "__dataclass_fields__"):
        return {key: (item.value if isinstance(item, Enum) else item) for key, item in value.__dict__.items()}
    raise TypeError(f"Unsupported record type: {type(value)!r}")
