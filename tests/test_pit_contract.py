from datetime import date

import pytest

from india_active_universe.api import CalendarStore, CompanyNameHistoryStore, CoverageError, DataPlatform, IsinHistoryStore, PriceStore, SecurityMaster, StatusStore, TerminalEventStore, UniverseStore
from india_active_universe.identity import apply_manual_overrides
from india_active_universe.models import DailyObservation
from india_active_universe.pipeline import build_active_snapshot, classify_instrument_type, discover_securities
from scripts.collect_nse_suspension_evidence import effective_date


def test_symbol_rename_is_date_sensitive():
    master = SecurityMaster([
        {"exchange": "NSE", "series": "EQ", "symbol": "ABC", "effective_from": date(2015, 1, 1), "effective_to": date(2018, 6, 30), "security_id": "SEC1"},
        {"exchange": "NSE", "series": "EQ", "symbol": "XYZ", "effective_from": date(2018, 7, 1), "effective_to": None, "security_id": "SEC1"},
    ])
    assert master.resolve_symbol("ABC", "2017-01-01")["security_id"] == "SEC1"
    assert master.resolve_symbol("XYZ", "2019-01-01")["security_id"] == "SEC1"


def test_effective_company_and_isin_histories_are_date_sensitive():
    names = CompanyNameHistoryStore([
        {"issuer_id": "ISS1", "company_name": "OLD NAME", "effective_from": "2010-01-01", "effective_to": "2015-12-31"},
        {"issuer_id": "ISS1", "company_name": "NEW NAME", "effective_from": "2016-01-01", "effective_to": None},
    ])
    isins = IsinHistoryStore([
        {"security_id": "SEC1", "isin": "OLDISIN", "effective_from": "2010-01-01", "effective_to": "2015-12-31"},
        {"security_id": "SEC1", "isin": "NEWISIN", "effective_from": "2016-01-01", "effective_to": None},
    ])
    assert names.name_at("ISS1", "2014-01-01") == "OLD NAME"
    assert names.name_at("ISS1", "2017-01-01") == "NEW NAME"
    assert isins.isin_at("SEC1", "2014-01-01") == "OLDISIN"
    assert isins.isin_at("SEC1", "2017-01-01") == "NEWISIN"


def test_approved_manual_override_is_explicitly_applied():
    identities = [{"security_id": "SEC1", "exchange": "NSE", "series": "EQ", "effective_from": date(2010, 1, 1), "effective_to": date(2020, 12, 31), "identity_quality": "PARTIAL"}]
    overrides = [{"exchange": "NSE", "symbol": "ABC", "series": "EQ", "effective_from": date(2015, 1, 1), "effective_to": date(2015, 12, 31), "security_id": "SEC1", "evidence_references": ["NSE_NOTICE_1"], "rationale": "Official symbol notice", "review_status": "APPROVED"}]
    matches = apply_manual_overrides(identities, overrides)
    assert len(identities) == 3
    assert identities[1]["identity_source"] == "MANUAL_APPROVED_OVERRIDE"
    assert identities[1]["symbol"] == "ABC"
    assert matches[0]["security_id"] == "SEC1"


def test_date_free_ambiguity_is_rejected():
    master = SecurityMaster([
        {"exchange": "NSE", "series": "EQ", "symbol": "ABC", "effective_from": date(2010, 1, 1), "effective_to": date(2014, 1, 1)},
        {"exchange": "NSE", "series": "EQ", "symbol": "ABC", "effective_from": date(2018, 1, 1), "effective_to": None},
    ])
    with pytest.raises(TypeError):
        master.resolve_symbol("ABC", None)  # type: ignore[arg-type]


def test_future_listing_cannot_enter_past_universe():
    store = UniverseStore([
        {"date": date(2020, 1, 1), "security_id": "OLD", "active": True},
        {"date": date(2020, 1, 1), "security_id": "NEW", "active": False},
    ])
    assert [row["security_id"] for row in store.active_on("2020-01-01")] == ["OLD"]


def test_active_snapshot_labels_no_trade_without_removing_the_row():
    rows = build_active_snapshot([{"date": date(2020, 1, 1), "security_id": "SEC1", "series": "EQ", "instrument_type": "ORDINARY_EQUITY", "raw_close": 10.0, "volume": 0}], date(2020, 1, 1))
    assert rows[0]["active"] is True
    assert rows[0]["observation_status"] == "NO_TRADE"


def test_status_lookup_is_effective_dated():
    store = StatusStore([
        {"security_id": "SEC1", "status_start": "2010-01-01", "status_end": "2014-12-31", "trading_status": "ACTIVE_TRADING"},
        {"security_id": "SEC1", "status_start": "2015-01-01", "status_end": "2017-06-30", "trading_status": "SUSPENDED"},
        {"security_id": "SEC1", "status_start": "2017-07-01", "status_end": None, "trading_status": "DELISTED"},
    ])
    assert store.status_on("2016-01-01")[0]["trading_status"] == "SUSPENDED"
    assert store.status_on("2018-01-01")[0]["trading_status"] == "DELISTED"


def test_suspension_effective_date_accepts_legacy_spacing():
    assert effective_date("The security will be suspended from trading w. e. f . May 22, 2015.") == "2015-05-22"


def test_observation_status_distinguishes_session_and_security_states():
    platform = DataPlatform()
    platform.security_master = SecurityMaster([{"security_id": "SEC1", "exchange": "NSE", "series": "EQ", "effective_from": "2020-01-01", "effective_to": "2020-01-03"}])
    platform.calendar = CalendarStore([{"date": "2020-01-02"}, {"date": "2020-01-03"}])
    platform.prices = PriceStore([{"security_id": "SEC1", "date": "2020-01-02", "volume": 0, "raw_close": 10.0}])
    assert platform.observation_status("SEC1", "2020-01-01") == "NO_MARKET_SESSION"
    assert platform.observation_status("SEC1", "2020-01-02") == "NO_TRADE"
    assert platform.observation_status("SEC1", "2020-01-03") == "UNKNOWN"


def test_strict_platform_rejects_out_of_range_dates():
    platform = DataPlatform(strict=True)
    platform.coverage_start = date(2006, 1, 2)
    platform.coverage_end = date(2026, 8, 10)
    platform.verified_start = date(2010, 1, 1)
    platform.verified_end = date(2020, 12, 31)
    platform.universe = UniverseStore([])
    with pytest.raises(CoverageError):
        platform.active_on("2009-12-31")


def test_raw_and_adjusted_history_are_separate():
    platform = DataPlatform()
    platform.prices = PriceStore([{"security_id": "SEC1", "date": "2020-01-01", "raw_close": 100.0}])
    platform.adjusted_prices = PriceStore([{"security_id": "SEC1", "date": "2020-01-01", "research_adjusted_close": 50.0}])
    assert platform.history("SEC1", "2020-01-01", "2020-01-01")[0]["raw_close"] == 100.0
    assert platform.adjusted_history("SEC1", "2020-01-01", "2020-01-01")[0]["research_adjusted_close"] == 50.0


def test_adjusted_history_series_is_explicit():
    platform = DataPlatform()
    platform.adjusted_prices = PriceStore([{"security_id": "SEC1", "date": "2020-01-01", "research_adjusted_close": 50.0, "research_adjusted_close_total_return": 55.0, "adjustment_quality": "PRICE_ACTION_ADJUSTED_VERIFIED", "total_return_quality": "TOTAL_RETURN_PARTIAL"}])
    assert platform.adjusted_history("SEC1", "2020-01-01", "2020-01-01", series="PRICE_RETURN")[0]["adjusted_close"] == 50.0
    assert platform.adjusted_history("SEC1", "2020-01-01", "2020-01-01", series="TOTAL_RETURN")[0]["adjusted_close"] == 55.0


def test_symbol_reuse_with_isin_creates_separate_discovery_records():
    observations = [
        DailyObservation(date(2010, 1, 1), "NSE", "REUSED", "EQ", None, None, None, None, None, None, None, "a.zip", "a", "NSE", "INEOLD"),
        DailyObservation(date(2015, 1, 1), "NSE", "REUSED", "EQ", None, None, None, None, None, None, None, "b.zip", "b", "NSE", "INENEW"),
    ]
    discovered = discover_securities(observations)
    assert {row["candidate_isin"] for row in discovered} == {"INEOLD", "INENEW"}


def test_explicit_etf_markers_are_not_ordinary_equity():
    assert classify_instrument_type("BANKBEES", "NIP IND ETF BANK BEES") == "ETF"
    assert classify_instrument_type("ABC", "ABC INDUSTRIES LIMITED") == "ORDINARY_EQUITY"


def test_terminal_recovery_scenarios_do_not_create_canonical_value():
    store = TerminalEventStore([{"security_id": "DEAD", "event_id": "E1", "terminal_event_type": "COMPULSORY_DELISTING", "terminal_value": None}])
    scenarios = store.recovery_scenarios("DEAD", last_observed_price=12.5)
    assert {row["scenario"] for row in scenarios} == {"ZERO_RECOVERY", "LAST_OBSERVED_PRICE"}
    assert all(row["canonical"] is False for row in scenarios)


def test_terminal_event_queue_accepts_downstream_holdings():
    store = TerminalEventStore([{"security_id": "DEAD", "event_id": "E1", "terminal_event_type": "UNKNOWN_TERMINAL_EVENT"}, {"security_id": "LIVE", "event_id": "E2"}])
    assert [row["event_id"] for row in store.resolution_queue_for_holdings(["DEAD"])] == ["E1"]


def test_optional_positive_volume_filter_is_downstream_only():
    store = UniverseStore([
        {"date": date(2020, 1, 1), "security_id": "A", "active": True, "close": 20.0, "history_sessions": 60, "zero_volume_days_60": 10, "median_traded_value_60": 6_000_000},
        {"date": date(2020, 1, 1), "security_id": "B", "active": True, "close": 20.0, "history_sessions": 60, "zero_volume_days_60": 5, "median_traded_value_60": 6_000_000},
    ])
    assert [row["security_id"] for row in store.eligible_on("2020-01-01", min_positive_volume_days_60=55)] == ["B"]


def test_calendar_returns_only_official_sessions():
    store = CalendarStore([{"date": "2020-01-02", "session_evidence": "OFFICIAL_NSE_MARKET_DATA"}, {"date": "2020-01-03", "session_evidence": "OFFICIAL_NSE_MARKET_DATA"}])
    assert [row["date"].isoformat() for row in store.sessions_between("2020-01-01", "2020-01-05")] == ["2020-01-02", "2020-01-03"]
