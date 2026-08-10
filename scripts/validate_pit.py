from __future__ import annotations

from datetime import date

from india_active_universe.adjustments import CorporateAction
from india_active_universe.identity import resolve_symbol
from india_active_universe.pit import active_as_of, adjustment_factors_as_of, liquidity_as_of


def row(point: date, security: str, symbol: str, *, value: float = 100.0) -> dict:
    return {"date": point, "security_id": security, "listing_episode_id": f"EP_{security}", "symbol_at_date": symbol, "series": "EQ", "instrument_type": "ORDINARY_EQUITY", "raw_close": value, "volume": 10, "traded_value": value * 10}


def main() -> None:
    t = date(2020, 1, 2)
    future = date(2020, 1, 3)
    historical = [row(t, "OLD", "OLDABC"), row(future, "NEW", "NEWXYZ")]
    assert [item["security_id"] for item in active_as_of(historical, t)] == ["OLD"], "future listing leakage"
    assert liquidity_as_of(historical, t)[0]["history_sessions"] == 1, "future liquidity leakage"
    assert [item["security_id"] for item in active_as_of(historical, future)] == ["NEW"], "active date semantics"

    rename = [
        {"exchange": "NSE", "series": "EQ", "symbol": "ABC", "effective_from": date(2010, 1, 1), "effective_to": date(2014, 12, 31), "security_id": "SEC1"},
        {"exchange": "NSE", "series": "EQ", "symbol": "XYZ", "effective_from": date(2015, 1, 1), "effective_to": None, "security_id": "SEC1"},
    ]
    assert resolve_symbol(rename, "ABC", date(2012, 1, 1))["security_id"] == resolve_symbol(rename, "XYZ", date(2016, 1, 1))["security_id"], "symbol rename continuity"
    reused = rename + [{"exchange": "NSE", "series": "EQ", "symbol": "ABC", "effective_from": date(2018, 1, 1), "effective_to": None, "security_id": "SEC2"}]
    assert resolve_symbol(reused, "ABC", date(2018, 1, 1))["security_id"] == "SEC2", "symbol reuse isolation"

    action = CorporateAction("A1", "OLD", date(2020, 1, 3), "BONUS", 0.5, 2.0, ("A1",), "OFFICIAL")
    factors = adjustment_factors_as_of([action], [date(2020, 1, 2)], date(2020, 1, 2))
    assert factors[0]["adjustment_factor"] == 1.0, "future corporate action leakage"
    before_exit = active_as_of([row(t, "DEAD", "DEAD")], t)
    assert before_exit[0]["security_id"] == "DEAD", "historical dead security removed"
    print("PIT_VALIDATION_OK")


if __name__ == "__main__":
    main()
