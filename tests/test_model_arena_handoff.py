from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from india_active_universe.api import DataPlatform


ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "releases" / "india_equity_data_v2.0.1"
REQUIRED_RELEASE_FILES = (
    "data_release_manifest.json",
    "research_universe_monthly.parquet",
    "daily_prices_adjusted.parquet",
    "daily_prices_raw.parquet",
    "trading_calendar.parquet",
    "terminal_events.parquet",
)
HANDOFF_DATES = ("2013-03-28", "2018-03-28", "2020-03-31", "2024-03-28", "2026-08-10")
MANDATORY_UNIVERSE_FIELDS = (
    "security_id",
    "listing_episode_id",
    "symbol_at_date",
    "instrument_type",
    "identity_quality",
    "price",
    "positive_volume_days_60",
    "median_traded_value_60",
    "median_traded_value_126",
    "liquidity_rank_126",
    "liquidity_percentile",
    "LIQUID_V1_eligible",
    "profile_id",
    "profile_version",
    "as_of_date",
    "eligibility_result",
    "eligibility_reason_codes",
)


def test_model_arena_handoff_reads_profile_history_liquidity_and_execution_prices():
    missing = [name for name in REQUIRED_RELEASE_FILES if not (RELEASE / name).exists()]
    if missing:
        pytest.skip(f"local data-scale release artifacts are not present: {', '.join(missing)}")

    platform = DataPlatform.from_release(RELEASE, strict=True)
    assert platform.coverage_end is not None

    for as_of in HANDOFF_DATES:
        universe = sorted(platform.profile_on(as_of, "LIQUID_V1"), key=lambda row: row["liquidity_rank_126"])
        assert universe, as_of

        candidates = universe[:5]
        for row in candidates:
            assert row["profile_id"] == "NSE_BROAD_LIQUID_PIT_V1"
            assert row["profile_version"] == "LIQUID_V1"
            assert row["eligibility_result"] == "ELIGIBLE"
            assert row["eligibility_reason_codes"] == "PASSED_LIQUID_V1"
            assert row["instrument_type"] == "ORDINARY_EQUITY"
            assert row["research_identity_ok"] is True
            assert row["price_adjustment_ok"] is True
            for field in MANDATORY_UNIVERSE_FIELDS:
                assert row.get(field) is not None, (as_of, row.get("security_id"), field)

        prior_sessions = platform.sessions_between("2006-01-02", as_of)
        assert len(prior_sessions) >= 300, as_of
        history_start = prior_sessions[-300]["date"]

        next_start = platform._check_date(as_of) + timedelta(days=1)
        next_sessions = []
        if next_start <= platform.coverage_end:
            next_sessions = platform.sessions_between(next_start, platform.coverage_end)

        for row in candidates[:3]:
            security_id = row["security_id"]
            adjusted = platform.adjusted_history(security_id, history_start, as_of, series="PRICE_RETURN")
            assert len(adjusted) == 300, (as_of, security_id)
            assert all(item.get("adjusted_close") is not None for item in adjusted)
            assert all(item.get("adjusted_quality") in {"NO_ADJUSTMENT_REQUIRED", "PRICE_ACTION_ADJUSTED_VERIFIED"} for item in adjusted)

            if next_sessions:
                next_date = next_sessions[0]["date"]
                raw_next = platform.history(security_id, next_date, next_date)
                assert raw_next, (as_of, security_id, next_date)
                for field in ("raw_open", "raw_high", "raw_low", "raw_close", "volume", "traded_value"):
                    assert raw_next[0].get(field) is not None, (as_of, security_id, next_date, field)
            else:
                assert as_of == platform.coverage_end.isoformat()

            scenarios = platform.terminal_recovery_scenarios(security_id)
            assert isinstance(scenarios, list)
