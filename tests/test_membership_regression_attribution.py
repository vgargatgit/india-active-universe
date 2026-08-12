from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from scripts.build_membership_regression_attribution import build_differences


def write_release(path: Path, monthly_rows: list[dict], price_rows: list[dict], ca_rows: list[dict] | None = None) -> None:
    path.mkdir()
    if not monthly_rows:
        dummy = monthly("DUMMY", top750=False, liquid=False)
        dummy["date"] = "2012-12-31"
        monthly_rows = [dummy]
    if not price_rows:
        dummy_price = price("DUMMY")
        dummy_price["date"] = "2012-12-31"
        price_rows = [dummy_price]
    if ca_rows is None:
        ca_rows = [
            {
                "security_id": "SEC_DUMMY",
                "event_date": "2012-12-31",
                "event_id": "NSE_CA_DUMMY",
                "event_type": "SPLIT",
                "price_factor": 1.0,
            }
        ]
    pq.write_table(pa.Table.from_pylist(monthly_rows), path / "research_universe_monthly.parquet")
    pq.write_table(pa.Table.from_pylist(price_rows), path / "daily_prices_adjusted.parquet")
    pq.write_table(pa.Table.from_pylist(ca_rows), path / "corporate_actions.parquet")


def monthly(symbol: str, *, top750: bool, liquid: bool = True, instrument: str = "ORDINARY_EQUITY", rank: int = 1) -> dict:
    return {
        "date": "2013-01-31",
        "security_id": f"SEC_{symbol}",
        "symbol_at_date": symbol,
        "isin": f"ISIN_{symbol}",
        "instrument_type": instrument,
        "trading_status": "ACTIVE_TRADING",
        "history_sessions": 300,
        "listing_age_sessions": 300,
        "positive_volume_days_60": 60,
        "median_traded_value_60": 10_000_000.0,
        "median_traded_value_126": 10_000_000.0,
        "rank_126": rank,
        "NSE_BROAD_LIQUID_PIT_V1_eligible": liquid,
        "top500_liquidity": rank <= 500,
        "top750_liquidity": top750,
        "top1000_liquidity": rank <= 1000,
        "research_identity_quality": "RECONSTRUCTED_HIGH_CONFIDENCE",
        "research_identity_ok": True,
        "price_adjustment_ok": True,
        "eligibility_result": "ELIGIBLE" if liquid else "NOT_ELIGIBLE",
    }


def price(symbol: str, value: float = 100.0) -> dict:
    return {
        "date": "2013-01-31",
        "security_id": f"SEC_{symbol}",
        "symbol_at_date": symbol,
        "research_adjusted_close": value,
    }


def test_known_membership_difference_gets_one_attribution(tmp_path: Path):
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    write_release(baseline, [monthly("KOTAKGOLD", top750=True, instrument="ETF")], [price("KOTAKGOLD")])
    write_release(candidate, [], [])

    summary = build_differences(baseline, candidate, tmp_path / "diffs.parquet", tmp_path / "signal.parquet")

    assert summary["totals"]["LIQUID_V1"] == 1
    assert summary["unexplained"] == {}
    assert any(row["primary_attribution"] == "NON_ORDINARY_INSTRUMENT_REMOVAL" for row in summary["attribution_counts"])


def test_rank_displacement_entrant_is_second_order(tmp_path: Path):
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    write_release(
        baseline,
        [monthly("KOTAKGOLD", top750=True, instrument="ETF", rank=750), monthly("ABC", top750=False, rank=751)],
        [price("KOTAKGOLD"), price("ABC")],
    )
    write_release(candidate, [monthly("ABC", top750=True, rank=750)], [price("ABC")])

    summary = build_differences(baseline, candidate, tmp_path / "diffs.parquet", tmp_path / "signal.parquet")

    assert any(row["primary_attribution"] == "RANK_CUTOFF_SECOND_ORDER_EFFECT" for row in summary["attribution_counts"])
    assert summary["unexplained"] == {}


def test_signal_price_unexplained_is_reported(tmp_path: Path):
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    write_release(baseline, [monthly("ABC", top750=True)], [price("ABC", 100.0)])
    write_release(candidate, [monthly("ABC", top750=True)], [price("ABC", 101.0)])

    summary = build_differences(baseline, candidate, tmp_path / "diffs.parquet", tmp_path / "signal.parquet")

    assert summary["signal_price"]["unexplained"] == 1
