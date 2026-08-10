from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class QualityFinding:
    check: str
    severity: str
    source_file_id: str | None
    security_id: str | None
    observed_date: str | None
    message: str


def validate_ohlc(open_: Decimal | None, high: Decimal | None, low: Decimal | None, close: Decimal | None, volume: int | None) -> list[str]:
    errors: list[str] = []
    values = [item for item in (open_, high, low, close) if item is not None]
    if any(value <= 0 for value in values):
        errors.append("NON_POSITIVE_PRICE")
    if volume is not None and volume < 0:
        errors.append("NEGATIVE_VOLUME")
    if high is not None and low is not None and low > high:
        errors.append("LOW_ABOVE_HIGH")
    if open_ is not None and high is not None and not open_ <= high:
        errors.append("OPEN_ABOVE_HIGH")
    if open_ is not None and low is not None and not low <= open_:
        errors.append("OPEN_BELOW_LOW")
    if close is not None and high is not None and not close <= high:
        errors.append("CLOSE_ABOVE_HIGH")
    if close is not None and low is not None and not low <= close:
        errors.append("CLOSE_BELOW_LOW")
    return errors
