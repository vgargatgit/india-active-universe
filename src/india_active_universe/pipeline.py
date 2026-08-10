from __future__ import annotations

from collections import defaultdict
from datetime import date
from statistics import median
from typing import Any, Iterable

from .models import DailyObservation, InstrumentType, TradingStatus
from .quality import QualityFinding, validate_ohlc


def discover_securities(observations: Iterable[DailyObservation]) -> list[dict[str, Any]]:
    """Discover historical exchange keys; never seed from a current master."""
    seen: dict[tuple[str, str, str], dict[str, Any]] = {}
    for observation in observations:
        key = (observation.exchange, observation.symbol, observation.series)
        row = seen.setdefault(key, {"exchange": observation.exchange, "symbol": observation.symbol, "series": observation.series, "instrument_type": InstrumentType.ORDINARY_EQUITY.value, "first_seen": observation.date, "last_seen": observation.date, "isins": set(), "company_names": set()})
        row["first_seen"] = min(row["first_seen"], observation.date)
        row["last_seen"] = max(row["last_seen"], observation.date)
        if observation.isin:
            row["isins"].add(observation.isin)
        if observation.company_name:
            row["company_names"].add(observation.company_name)
    output = []
    for row in seen.values():
        output.append({**row, "candidate_isin": next(iter(row["isins"])) if len(row["isins"]) == 1 else None, "company_name": next(iter(row["company_names"])) if row["company_names"] else None})
        output[-1].pop("isins")
        output[-1].pop("company_names")
    return sorted(output, key=lambda row: (row["first_seen"], row["symbol"], row["series"]))


def validate_observations(observations: Iterable[DailyObservation]) -> list[QualityFinding]:
    findings: list[QualityFinding] = []
    keys: set[tuple[date, str, str, str]] = set()
    for row in observations:
        key = (row.date, row.exchange, row.symbol, row.series)
        if key in keys:
            findings.append(QualityFinding("DUPLICATE_OBSERVATION", "ERROR", row.source_file_id, row.security_id, row.date.isoformat(), "Duplicate exchange observation key"))
        keys.add(key)
        for error in validate_ohlc(row.open, row.high, row.low, row.close, row.volume):
            findings.append(QualityFinding(error, "ERROR", row.source_file_id, row.security_id, row.date.isoformat(), "OHLCV invariant failed"))
    return findings


def build_active_snapshot(observations: Iterable[dict[str, Any]], as_of_date: date) -> list[dict[str, Any]]:
    """Materialize ACTIVE_V1 using only rows dated exactly at the requested session."""
    result = []
    for row in observations:
        close = row.get("close", row.get("raw_close"))
        if row.get("date") == as_of_date and row.get("instrument_type", InstrumentType.ORDINARY_EQUITY.value) == InstrumentType.ORDINARY_EQUITY.value and row.get("series") == "EQ" and close is not None:
            result.append({**row, "close": close, "trading_status": TradingStatus.ACTIVE_TRADING.value, "active": True, "active_definition_version": "ACTIVE_V1"})
    return result


def liquidity_features(rows: Iterable[dict[str, Any]], *, window: int = 60) -> list[dict[str, Any]]:
    by_security: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_security[row["security_id"]].append(row)
    output = []
    for security_id, history in by_security.items():
        history.sort(key=lambda row: row["date"])
        for index, row in enumerate(history):
            window_rows = history[max(0, index - window + 1):index + 1]
            values = [item["traded_value"] for item in window_rows if item.get("traded_value") is not None]
            positive_volume = sum(1 for item in window_rows if (item.get("volume") or 0) > 0)
            output.append({**row, "history_sessions": index + 1, "valid_trade_days_60": len(values), "zero_volume_days_60": len(window_rows) - positive_volume, "median_traded_value_60": median(values) if values else None, "feature_as_of_date": row["date"]})
    return output


def build_active_universe(observations: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build daily ACTIVE_V1 rows from observed records, never from a current list."""
    by_date: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for row in observations:
        by_date[row["date"]].append(row)
    return [row for point in sorted(by_date) for row in build_active_snapshot(by_date[point], point)]
