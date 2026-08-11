from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import pytest
import pyarrow.parquet as parquet

from india_active_universe.api import DataPlatform
from india_active_universe.profiles import (
    ADJUSTED_PRICE_ARTIFACT,
    DATA_RELEASE_MANIFEST_ARTIFACT,
    RAW_EXECUTION_PRICE_ARTIFACT,
    RESEARCH_UNIVERSE_MONTHLY_ARTIFACT,
    TERMINAL_EVENTS_ARTIFACT,
    TRADING_CALENDAR_ARTIFACT,
    LIQUID_V1_DEFINITION,
    PROFILE_ID,
    PROFILE_VERSION,
    SOURCE_OBSERVED_START_DATE,
    TARGET_RELEASE_ID,
)


ROOT = Path(__file__).resolve().parents[1]
RELEASE_ID = os.environ.get("INDIA_EQUITY_DATA_RELEASE_ID", TARGET_RELEASE_ID)
RELEASE = ROOT / "releases" / RELEASE_ID
REQUIRED_RELEASE_FILES = (
    DATA_RELEASE_MANIFEST_ARTIFACT,
    RESEARCH_UNIVERSE_MONTHLY_ARTIFACT,
    ADJUSTED_PRICE_ARTIFACT,
    RAW_EXECUTION_PRICE_ARTIFACT,
    TRADING_CALENDAR_ARTIFACT,
    TERMINAL_EVENTS_ARTIFACT,
)
BASE_HANDOFF_DATES = ("2013-03-28", "2018-03-28", "2020-03-31", "2024-03-28")
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

    handoff_dates = [
        as_of for as_of in BASE_HANDOFF_DATES
        if platform.verified_start <= platform._check_date(as_of) <= platform.coverage_end
    ]
    handoff_dates.append(platform.coverage_end.isoformat())

    for as_of in handoff_dates:
        universe = sorted(platform.profile_on(as_of, PROFILE_VERSION), key=lambda row: row["liquidity_rank_126"])
        assert universe, as_of

        candidates = universe[:5]
        for row in candidates:
            assert row["profile_id"] == PROFILE_ID
            assert row["profile_version"] == PROFILE_VERSION
            assert row["eligibility_result"] == "ELIGIBLE"
            assert row["eligibility_reason_codes"] == f"PASSED_{PROFILE_VERSION}"
            assert row["instrument_type"] == LIQUID_V1_DEFINITION["instrument_type"]
            assert row["research_identity_ok"] is True
            assert row["price_adjustment_ok"] is True
            for field in MANDATORY_UNIVERSE_FIELDS:
                assert row.get(field) is not None, (as_of, row.get("security_id"), field)

        prior_sessions = platform.sessions_between(SOURCE_OBSERVED_START_DATE, as_of)
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


def _earliest_promoted_pre2013_snapshot(platform: DataPlatform) -> str | None:
    intervals = [
        interval for interval in platform.research_quality_intervals
        if interval.get("status") == "RESEARCH_HIGH_CONFIDENCE"
        and interval.get("start")
        and platform._check_date(interval["start"]) < date(2013, 1, 1)
    ]
    if not intervals:
        return None
    first_start = min(platform._check_date(interval["start"]) for interval in intervals)
    last_pre2013 = date(2012, 12, 31)
    snapshot_dates = sorted({
        platform._check_date(row["date"])
        for row in parquet.read_table(RELEASE / RESEARCH_UNIVERSE_MONTHLY_ARTIFACT, columns=["date"]).to_pylist()
        if first_start <= platform._check_date(row["date"]) <= last_pre2013
    })
    return snapshot_dates[0].isoformat() if snapshot_dates else None


def test_model_arena_handoff_reads_earliest_promoted_pre2013_interval():
    missing = [name for name in REQUIRED_RELEASE_FILES if not (RELEASE / name).exists()]
    if missing:
        pytest.skip(f"local data-scale release artifacts are not present: {', '.join(missing)}")

    platform = DataPlatform.from_release(RELEASE, strict=True)
    as_of = _earliest_promoted_pre2013_snapshot(platform)
    if as_of is None:
        pytest.skip("release does not publish a pre-2013 RESEARCH_HIGH_CONFIDENCE interval")

    universe = sorted(platform.profile_on(as_of, PROFILE_VERSION), key=lambda row: row["liquidity_rank_126"])
    assert universe, as_of

    candidates = universe[:5]
    for row in candidates:
        assert row["profile_id"] == PROFILE_ID
        assert row["profile_version"] == PROFILE_VERSION
        assert row["eligibility_result"] == "ELIGIBLE"
        assert row["eligibility_reason_codes"] == f"PASSED_{PROFILE_VERSION}"
        assert row["instrument_type"] == LIQUID_V1_DEFINITION["instrument_type"]
        assert row["research_identity_ok"] is True
        assert row["price_adjustment_ok"] is True
        assert row["feature_ready_60"] is True
        assert row["feature_ready_126"] is True
        assert row["signal_history_ready_252"] is True
        assert row["signal_history_ready_273"] is True
        assert row["model_handoff_history_ready_300"] is True
        for field in MANDATORY_UNIVERSE_FIELDS:
            assert row.get(field) is not None, (as_of, row.get("security_id"), field)

    prior_sessions = platform.sessions_between(SOURCE_OBSERVED_START_DATE, as_of)
    assert len(prior_sessions) >= 300, as_of
    history_start = prior_sessions[-300]["date"]
    next_sessions = platform.sessions_between(platform._check_date(as_of) + timedelta(days=1), platform.coverage_end)
    assert next_sessions, as_of
    next_date = next_sessions[0]["date"]

    for row in candidates[:3]:
        security_id = row["security_id"]
        adjusted = platform.adjusted_history(security_id, history_start, as_of, series="PRICE_RETURN")
        assert len(adjusted) == 300, (as_of, security_id)
        assert all(item.get("adjusted_close") is not None for item in adjusted)
        assert all(item.get("adjusted_quality") in {"NO_ADJUSTMENT_REQUIRED", "PRICE_ACTION_ADJUSTED_VERIFIED"} for item in adjusted)

        raw_next = platform.history(security_id, next_date, next_date)
        assert raw_next, (as_of, security_id, next_date)
        for field in ("raw_open", "raw_high", "raw_low", "raw_close", "volume", "traded_value"):
            assert raw_next[0].get(field) is not None, (as_of, security_id, next_date, field)
