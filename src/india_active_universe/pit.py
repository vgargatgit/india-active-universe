from __future__ import annotations

from datetime import date
from typing import Any, Iterable

from .adjustments import CorporateAction, cumulative_price_factors
from .pipeline import build_active_snapshot, liquidity_features


def active_as_of(observations: Iterable[dict[str, Any]], point: date) -> list[dict[str, Any]]:
    return build_active_snapshot(observations, point)


def liquidity_as_of(observations: Iterable[dict[str, Any]], point: date, *, window: int = 60) -> list[dict[str, Any]]:
    bounded = [row for row in observations if row["date"] <= point]
    return [row for row in liquidity_features(bounded, window=window) if row["date"] == point]


def adjustment_factors_as_of(actions: Iterable[CorporateAction], dates: Iterable[date], point: date) -> list[dict[str, Any]]:
    eligible = [action for action in actions if action.effective_date <= point]
    return cumulative_price_factors(eligible, dates)
