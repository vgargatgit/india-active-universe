from datetime import date

import pytest

from india_active_universe.api import CoverageError, DataPlatform, SecurityMaster, StatusStore, UniverseStore


def test_symbol_rename_is_date_sensitive():
    master = SecurityMaster([
        {"exchange": "NSE", "series": "EQ", "symbol": "ABC", "effective_from": date(2015, 1, 1), "effective_to": date(2018, 6, 30), "security_id": "SEC1"},
        {"exchange": "NSE", "series": "EQ", "symbol": "XYZ", "effective_from": date(2018, 7, 1), "effective_to": None, "security_id": "SEC1"},
    ])
    assert master.resolve_symbol("ABC", "2017-01-01")["security_id"] == "SEC1"
    assert master.resolve_symbol("XYZ", "2019-01-01")["security_id"] == "SEC1"


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


def test_status_lookup_is_effective_dated():
    store = StatusStore([
        {"security_id": "SEC1", "status_start": "2010-01-01", "status_end": "2014-12-31", "trading_status": "ACTIVE_TRADING"},
        {"security_id": "SEC1", "status_start": "2015-01-01", "status_end": "2017-06-30", "trading_status": "SUSPENDED"},
        {"security_id": "SEC1", "status_start": "2017-07-01", "status_end": None, "trading_status": "DELISTED"},
    ])
    assert store.status_on("2016-01-01")[0]["trading_status"] == "SUSPENDED"
    assert store.status_on("2018-01-01")[0]["trading_status"] == "DELISTED"


def test_strict_platform_rejects_out_of_range_dates():
    platform = DataPlatform(strict=True)
    platform.coverage_start = date(2006, 1, 2)
    platform.coverage_end = date(2026, 8, 10)
    platform.universe = UniverseStore([])
    with pytest.raises(CoverageError):
        platform.active_on("2006-01-01")
