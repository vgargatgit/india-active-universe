from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable


@dataclass(frozen=True)
class CorporateAction:
    event_id: str
    security_id: str
    effective_date: date
    event_type: str
    price_factor: float
    share_factor: float | None
    source_event_ids: tuple[str, ...]
    quality: str


def cumulative_price_factors(actions: Iterable[CorporateAction], dates: Iterable[date]) -> list[dict[str, Any]]:
    """Return backward-looking factors without rewriting nominal exchange prices.

    Factors are intentionally event-driven; unexplained price jumps are not
    converted into corporate actions by this function.
    """
    ordered_actions = sorted(actions, key=lambda action: action.effective_date)
    factor = 1.0
    output = []
    for point in sorted(dates):
        for action in ordered_actions:
            if action.effective_date > point:
                factor *= action.price_factor
        output.append({"date": point, "adjustment_factor": factor, "factor_reason": "OFFICIAL_CORPORATE_ACTION", "source_event_ids": [action.event_id for action in ordered_actions if action.effective_date > point]})
    return output


def apply_price_adjustment(raw_close: float | None, factor: float | None) -> float | None:
    return None if raw_close is None or factor is None else raw_close * factor
