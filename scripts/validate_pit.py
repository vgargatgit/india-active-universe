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

    liquidity_history = [
        row(date(2020, 1, 1), "A", "A", value=10.0),
        row(t, "A", "A", value=20.0),
        row(date(2020, 1, 1), "B", "B", value=30.0),
        row(t, "B", "B", value=40.0),
        row(future, "A", "A", value=1_000_000.0),
        row(future, "B", "B", value=1.0),
    ]
    perturbed = [
        {**item, "raw_close": 999_999_999.0, "traded_value": 999_999_999.0, "volume": 999_999_999}
        if item["date"] > t else item
        for item in liquidity_history
    ]
    base_features = {item["security_id"]: item["median_traded_value_60"] for item in liquidity_as_of(liquidity_history, t)}
    perturbed_features = {item["security_id"]: item["median_traded_value_60"] for item in liquidity_as_of(perturbed, t)}
    assert base_features == perturbed_features, "future liquidity perturbation changed PIT features"
    base_rank = sorted(base_features, key=base_features.get, reverse=True)
    perturbed_rank = sorted(perturbed_features, key=perturbed_features.get, reverse=True)
    assert base_rank == perturbed_rank, "future liquidity perturbation changed PIT ranking"

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
