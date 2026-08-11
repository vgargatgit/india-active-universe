import json
from datetime import date

import pytest

from india_active_universe.api import CalendarStore, CompanyNameHistoryStore, CoverageError, DataPlatform, IsinHistoryStore, ParquetUniverseStore, PriceStore, SecurityMaster, StatusStore, TerminalEventStore, UniverseStore
from india_active_universe.identity import apply_manual_overrides, load_manual_overrides
from india_active_universe.models import DailyObservation
from india_active_universe.pipeline import build_active_snapshot, classify_instrument_type, discover_securities
from india_active_universe.profiles import (
    ACTIVE_DEFINITION,
    COMPONENT_QUALITY,
    DATASET_QUALITY_TIER,
    EXECUTION_POLICY,
    LIQUIDITY_ARTIFACT,
    LIQUID_V1_DEFINITION,
    PRIORITY_SCOPE,
    PROFILE_ID,
    PROFILE_VERSION,
    PARSER_VERSIONS,
    RAW_EXECUTION_PRICE_ARTIFACT,
    RECOMMENDED_SIGNAL_PRICE_SERIES,
    RESEARCH_HIGH_CONFIDENCE_STATUS,
    RESEARCH_MANIFEST_ARTIFACTS,
    RESEARCH_MONTHLY_SNAPSHOT_START,
    RESEARCH_START_DATE,
    REQUIRED_QUALITY_THRESHOLD,
    SIGNAL_POLICY,
    SOURCE_BUILD_MODE,
    SOURCE_MANIFEST_ARTIFACT,
    TARGET_RELEASE_ID,
    TERMINAL_VALUE_POLICY,
    TERMINAL_VALUE_POLICY_REQUIREMENT,
    TOP_LIQUIDITY_RANKING_METRIC,
)
from scripts.build_completion_audit import REQUIRED, REQUIRED_RESEARCH_REPORTS, data_manifest_contract_failures, invariant_validation_summary, research_manifest_contract_failures
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


def test_adjacent_manual_overrides_are_allowed(tmp_path):
    pytest.importorskip("yaml")
    path = tmp_path / "manual_identity_overrides.yaml"
    path.write_text(
        """
overrides:
  - exchange: NSE
    symbol: ABC
    series: EQ
    effective_from: 2015-01-01
    effective_to: 2015-06-30
    security_id: SEC1
    evidence_references: [NSE_NOTICE_1]
    rationale: First official dated symbol notice
    review_status: APPROVED
  - exchange: NSE
    symbol: ABC
    series: EQ
    effective_from: 2015-07-01
    effective_to: 2015-12-31
    security_id: SEC1
    evidence_references: [NSE_NOTICE_2]
    rationale: Adjacent official dated symbol notice
    review_status: APPROVED
""",
        encoding="utf-8",
    )
    overrides = load_manual_overrides(path)
    assert [(row["effective_from"], row["effective_to"]) for row in overrides] == [
        (date(2015, 1, 1), date(2015, 6, 30)),
        (date(2015, 7, 1), date(2015, 12, 31)),
    ]


def test_overlapping_manual_overrides_are_rejected(tmp_path):
    pytest.importorskip("yaml")
    path = tmp_path / "manual_identity_overrides.yaml"
    path.write_text(
        """
overrides:
  - exchange: NSE
    symbol: ABC
    series: EQ
    effective_from: 2015-01-01
    effective_to: 2015-07-31
    security_id: SEC1
    evidence_references: [NSE_NOTICE_1]
    rationale: First official dated symbol notice
    review_status: APPROVED
  - exchange: NSE
    symbol: ABC
    series: EQ
    effective_from: 2015-07-01
    effective_to: 2015-12-31
    security_id: SEC2
    evidence_references: [NSE_NOTICE_2]
    rationale: Overlapping official dated symbol notice
    review_status: APPROVED
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="overlapping manual override range"):
        load_manual_overrides(path)


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


def test_strict_platform_uses_research_verified_range_for_release(tmp_path):
    import json
    import pyarrow as pa
    import pyarrow.parquet as pq

    release = tmp_path / "india_equity_data_test"
    release.mkdir()
    (release / "data_release_manifest.json").write_text(
        json.dumps(
            {
                "coverage": {"observed_start": "2006-01-02", "observed_end": "2026-08-10"},
                "verified_start_date": "2006-01-02",
                "verified_end_date": "2026-08-10",
                "quality_tier": "DATASET_EXPLORATORY",
            }
        ),
        encoding="utf-8",
    )
    (release / "research_release_manifest.json").write_text(
        json.dumps(
            {
                "research_quality": {
                    "status": RESEARCH_HIGH_CONFIDENCE_STATUS,
                    "start": RESEARCH_START_DATE,
                    "end": "2026-08-10",
                }
            }
        ),
        encoding="utf-8",
    )
    pq.write_table(pa.table({"security_id": []}), release / "security_master.parquet")
    for name in ("active_universe_daily.parquet", "liquidity_features.parquet", "daily_prices_raw.parquet"):
        pq.write_table(pa.table({"date": [], "security_id": []}), release / name)

    platform = DataPlatform.from_release(release, strict=True)
    assert platform.verified_start == date.fromisoformat(RESEARCH_START_DATE)
    assert platform.quality_tier == RESEARCH_HIGH_CONFIDENCE_STATUS
    with pytest.raises(CoverageError):
        platform.active_on("2012-12-31")


def test_research_manifest_contract_requires_scoped_downstream_policy(tmp_path):
    release = tmp_path / TARGET_RELEASE_ID
    release.mkdir()
    data_manifest = {
        "release_id": release.name,
        "git_commit": "abc123",
        "build_mode": SOURCE_BUILD_MODE,
        "coverage": {"observed_start": "2006-01-02", "observed_end": "2026-08-10"},
    }
    valid_manifest = {
        "release_id": release.name,
        "git_sha": "abc123",
        "research_quality": {
            "status": RESEARCH_HIGH_CONFIDENCE_STATUS,
            "start": RESEARCH_START_DATE,
            "end": "2026-08-10",
            "monthly_snapshot_start": RESEARCH_MONTHLY_SNAPSHOT_START,
            "universe_profile": PROFILE_ID,
            "profile_version": PROFILE_VERSION,
            "priority_scope": PRIORITY_SCOPE,
        },
        "source_coverage": {
            "observed_start": "2006-01-02",
            "observed_end": "2026-08-10",
            "research_start": RESEARCH_START_DATE,
            "research_end": "2026-08-10",
        },
        "known_policy": {
            "signals": SIGNAL_POLICY,
            "execution": EXECUTION_POLICY,
            "terminal_values": TERMINAL_VALUE_POLICY,
        },
        "required_quality_threshold": REQUIRED_QUALITY_THRESHOLD,
        "recommended_signal_price_series": RECOMMENDED_SIGNAL_PRICE_SERIES,
        "raw_execution_price_artifact": RAW_EXECUTION_PRICE_ARTIFACT,
        "liquidity_artifact": LIQUIDITY_ARTIFACT,
        "top_liquidity_ranking_metric": TOP_LIQUIDITY_RANKING_METRIC,
        "liquid_v1_definition": LIQUID_V1_DEFINITION,
        "terminal_value_policy_requirement": TERMINAL_VALUE_POLICY_REQUIREMENT,
        "required_research_securities": 10,
        "identity_failures": 0,
        "material_price_action_missing_factors": 0,
        "material_price_action_unresolved_boundaries": 0,
        "research_universe_monthly_contract": [
            "date",
            "security_id",
            "listing_episode_id",
            "symbol_at_date",
            "instrument_type",
            "identity_quality",
            "price",
            "history_sessions",
            "positive_volume_days_60",
            "median_traded_value_60",
            "median_traded_value_126",
            "liquidity_rank_126",
            "liquidity_percentile",
            "LIQUID_V1_eligible",
            "NSE_BROAD_LIQUID_PIT_V1_eligible",
            "top500_liquidity",
            "top750_liquidity",
            "top1000_liquidity",
            "research_identity_ok",
            "price_adjustment_quality",
            "price_adjustment_ok",
            "status_quality",
            "profile_id",
            "profile_version",
            "as_of_date",
            "eligibility_result",
            "eligibility_reason_codes",
        ],
        "required_research_security_contract": [
            "security_id",
            "first_research_date",
            "last_research_date",
            "enters_liquid_v1",
            "enters_top750",
            "best_rank_126",
            "worst_rank_126",
            "max_median_traded_value_60",
            "max_median_traded_value_126",
            "max_positive_volume_days_60",
            "research_identity_quality",
            "price_adjustment_quality",
            "price_adjustment_ok",
            "instrument_type",
            "instrument_type_quality",
            "status_quality",
            "active_trading_ok",
        ],
        "artifacts": {name: "0" * 64 for name in RESEARCH_MANIFEST_ARTIFACTS},
        "config_sha256": "0" * 64,
        "manual_override_sha256": "0" * 64,
        "partitioned_artifacts_manifest_sha256": "0" * 64,
        "research_invariant_validation_sha256": "0" * 64,
        "test_result_sha256": "0" * 64,
        "ci_status_sha256": "0" * 64,
        "quality_reports": {name: "0" * 64 for name in REQUIRED_RESEARCH_REPORTS},
        "known_limitations": [
            "Complete archive remains exploratory outside the scoped research universe.",
            "Terminal-event and terminal-value history is partial.",
            "Dividend and total-return coverage is partial.",
            "Historical market-cap data is not fabricated.",
            "Historical sector data is not fabricated.",
            "Retrieval timestamps may reflect local file metadata.",
        ],
    }

    assert research_manifest_contract_failures(release, data_manifest, valid_manifest) == []

    incomplete = {**valid_manifest, "known_limitations": ["Terminal values are partial."]}
    failures = research_manifest_contract_failures(release, data_manifest, incomplete)
    assert "research manifest known_limitations are incomplete" in failures
    assert any("market-cap" in failure for failure in failures)

    missing_artifact_contract = {**valid_manifest, "liquidity_artifact": "research_universe_monthly.parquet"}
    failures = research_manifest_contract_failures(release, data_manifest, missing_artifact_contract)
    assert "research manifest liquidity_artifact is not liquidity_features.parquet" in failures

    loose_liquid_v1_contract = {
        **valid_manifest,
        "liquid_v1_definition": {**valid_manifest["liquid_v1_definition"], "positive_volume_days_60_min": 30},
    }
    failures = research_manifest_contract_failures(release, data_manifest, loose_liquid_v1_contract)
    assert "research manifest liquid_v1_definition is not the published LIQUID_V1 contract" in failures

    missing_unresolved_artifact_hash = {
        **valid_manifest,
        "artifacts": {
            name: digest for name, digest in valid_manifest["artifacts"].items()
            if name != "unresolved_observed_trading.parquet"
        },
    }
    failures = research_manifest_contract_failures(release, data_manifest, missing_unresolved_artifact_hash)
    assert "research manifest artifact hash missing for unresolved_observed_trading.parquet" in failures

    stale_coverage = {
        **valid_manifest,
        "source_coverage": {**valid_manifest["source_coverage"], "observed_end": "2025-12-31"},
    }
    failures = research_manifest_contract_failures(release, data_manifest, stale_coverage)
    assert "source_coverage.observed_end does not match data manifest coverage" in failures

    missing_ci_status_hash = {key: value for key, value in valid_manifest.items() if key != "ci_status_sha256"}
    failures = research_manifest_contract_failures(release, data_manifest, missing_ci_status_hash)
    assert "research manifest ci_status_sha256 is missing or invalid" in failures

    missing_partition_hash = {key: value for key, value in valid_manifest.items() if key != "partitioned_artifacts_manifest_sha256"}
    failures = research_manifest_contract_failures(release, data_manifest, missing_partition_hash)
    assert "research manifest partitioned_artifacts_manifest_sha256 is missing or invalid" in failures

    unresolved_price_action = {**valid_manifest, "material_price_action_unresolved_boundaries": 1}
    failures = research_manifest_contract_failures(release, data_manifest, unresolved_price_action)
    assert "research manifest material_price_action_unresolved_boundaries is not zero" in failures

    missing_raw_report_hash = {
        **valid_manifest,
        "quality_reports": {
            name: digest for name, digest in valid_manifest["quality_reports"].items()
            if name != "raw_integrity_audit.md"
        },
    }
    failures = research_manifest_contract_failures(release, data_manifest, missing_raw_report_hash)
    assert "research manifest quality report hash missing for raw_integrity_audit.md" in failures

    missing_required_security_field = {
        **valid_manifest,
        "required_research_security_contract": [
            field for field in valid_manifest["required_research_security_contract"]
            if field != "price_adjustment_ok"
        ],
    }
    failures = research_manifest_contract_failures(release, data_manifest, missing_required_security_field)
    assert any("required_research_security_contract" in failure and "price_adjustment_ok" in failure for failure in failures)

    missing_monthly_field = {
        **valid_manifest,
        "research_universe_monthly_contract": [
            field for field in valid_manifest["research_universe_monthly_contract"]
            if field != "LIQUID_V1_eligible"
        ],
    }
    failures = research_manifest_contract_failures(release, data_manifest, missing_monthly_field)
    assert any("research_universe_monthly_contract" in failure and "LIQUID_V1_eligible" in failure for failure in failures)


def test_data_manifest_contract_requires_release_provenance(tmp_path):
    release = tmp_path / TARGET_RELEASE_ID
    release.mkdir()
    manifest = {
        "release_id": release.name,
        "git_commit": "abc123",
        "coverage": {
            "observed_start": "2006-01-02",
            "observed_end": "2026-08-10",
            "security_count": 2,
            "observation_count": 3,
        },
        "source_coverage": {
            "source_verified_start": "2006-01-02",
            "source_verified_end": "2026-08-10",
            "verification_basis": "official NSE market-data files; no independent exchange calendar claim",
        },
        "research_coverage": {
            "research_verified_start": RESEARCH_START_DATE,
            "research_verified_end": "2026-08-10",
            "universe_profile": PROFILE_ID,
            "profile_version": PROFILE_VERSION,
            "priority_scope": PRIORITY_SCOPE,
        },
        "component_quality": COMPONENT_QUALITY,
        "source_manifest_sha256": "0" * 64,
        "config_sha256": "0" * 64,
        "manual_override_sha256": "0" * 64,
        "definition": ACTIVE_DEFINITION,
        "quality_tier": DATASET_QUALITY_TIER,
        "parser_versions": PARSER_VERSIONS,
        "artifacts": {
            **{f"release/{name}": "0" * 64 for name in REQUIRED if name not in {"data_release_manifest.json", "research_release_manifest.json"}},
            f"release/{SOURCE_MANIFEST_ARTIFACT}": "0" * 64,
        },
    }

    assert data_manifest_contract_failures(release, manifest) == []

    incomplete = {**manifest, "manual_override_sha256": None}
    failures = data_manifest_contract_failures(release, incomplete)
    assert "data manifest manual_override_sha256 is missing or invalid" in failures

    missing_component_quality = {
        **manifest,
        "component_quality": {**manifest["component_quality"], "research_universe_2013_onward": "DATASET_EXPLORATORY"},
    }
    failures = data_manifest_contract_failures(release, missing_component_quality)
    assert "data manifest component_quality.research_universe_2013_onward is not RESEARCH_HIGH_CONFIDENCE" in failures

    stale_parser = {
        **manifest,
        "parser_versions": {**manifest["parser_versions"], "canonicalization": "identity-old"},
    }
    failures = data_manifest_contract_failures(release, stale_parser)
    assert f"data manifest parser_versions.canonicalization is not {PARSER_VERSIONS['canonicalization']}" in failures

    missing_release_hash = {
        **manifest,
        "artifacts": {
            key: value for key, value in manifest["artifacts"].items()
            if key != "release/unresolved_observed_trading.parquet"
        },
    }
    failures = data_manifest_contract_failures(release, missing_release_hash)
    assert "data manifest artifact hash missing for release/unresolved_observed_trading.parquet" in failures


def test_invariant_validation_summary_reports_nonzero_metrics_as_failures(tmp_path):
    report = tmp_path / "research_invariant_validation.json"
    report.write_text(
        json.dumps(
            {
                "status": "FAIL",
                "duplicate_month_security_rows": 0,
                "required_artifact_identity_quality_failures": 2,
            }
        ),
        encoding="utf-8",
    )

    summary = invariant_validation_summary(report)

    assert summary["status"] == "FAIL"
    assert summary["failure_count"] == 1
    assert summary["failures"] == {"required_artifact_identity_quality_failures": 2}


def test_raw_and_adjusted_history_are_separate():
    platform = DataPlatform()
    platform.prices = PriceStore([{"security_id": "SEC1", "date": "2020-01-01", "raw_close": 100.0}])
    platform.adjusted_prices = PriceStore([{"security_id": "SEC1", "date": "2020-01-01", "research_adjusted_close": 50.0}])
    assert platform.history("SEC1", "2020-01-01", "2020-01-01")[0]["raw_close"] == 100.0
    assert platform.adjusted_history("SEC1", "2020-01-01", "2020-01-01")[0]["research_adjusted_close"] == 50.0


def test_adjusted_history_series_is_explicit():
    platform = DataPlatform()
    platform.adjusted_prices = PriceStore([{"security_id": "SEC1", "date": "2020-01-01", "price_return_adjusted_close": 50.0, "total_return_adjusted_close": 55.0, "adjustment_quality": "PRICE_ACTION_ADJUSTED_VERIFIED", "total_return_quality": "TOTAL_RETURN_PARTIAL"}])
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


def test_platform_terminal_event_queue_accepts_downstream_holdings():
    platform = DataPlatform()
    platform.terminal_events = TerminalEventStore([
        {"security_id": "DEAD", "event_id": "E1", "terminal_event_type": "UNKNOWN_TERMINAL_EVENT"},
        {"security_id": "LIVE", "event_id": "E2"},
    ])
    queue = platform.terminal_event_resolution_queue_for_holdings(["DEAD"])
    assert [row["event_id"] for row in queue] == ["E1"]


def test_optional_positive_volume_filter_is_downstream_only():
    store = UniverseStore([
        {"date": date(2020, 1, 1), "security_id": "A", "active": True, "close": 20.0, "history_sessions": 60, "zero_volume_days_60": 10, "median_traded_value_60": 6_000_000},
        {"date": date(2020, 1, 1), "security_id": "B", "active": True, "close": 20.0, "history_sessions": 60, "zero_volume_days_60": 5, "median_traded_value_60": 6_000_000},
    ])
    assert [row["security_id"] for row in store.eligible_on("2020-01-01", min_positive_volume_days_60=55)] == ["B"]


def test_positive_volume_filter_uses_session_correct_feature_when_present():
    store = UniverseStore([
        {
            "date": date(2020, 1, 1),
            "security_id": "SPARSE",
            "active": True,
            "close": 20.0,
            "history_sessions": 60,
            "positive_volume_days_60": 35,
            "zero_volume_days_60": 5,
            "absent_observation_days_60": 20,
            "median_traded_value_60": 6_000_000,
        },
        {
            "date": date(2020, 1, 1),
            "security_id": "LIQUID",
            "active": True,
            "close": 20.0,
            "history_sessions": 60,
            "positive_volume_days_60": 40,
            "zero_volume_days_60": 0,
            "absent_observation_days_60": 20,
            "median_traded_value_60": 6_000_000,
        },
    ])
    eligible = store.eligible_on("2020-01-01", min_positive_volume_days_60=40)
    assert [row["security_id"] for row in eligible] == ["LIQUID"]


def test_profile_on_adds_downstream_audit_metadata():
    store = UniverseStore([
        {
            "date": date(2020, 1, 1),
            "security_id": "LIQUID",
            "active": True,
            "NSE_BROAD_LIQUID_PIT_V1_eligible": True,
        }
    ])
    row = store.profile_on("2020-01-01", PROFILE_VERSION)[0]
    assert row["profile_id"] == PROFILE_ID
    assert row["profile_version"] == PROFILE_VERSION
    assert row["as_of_date"] == date(2020, 1, 1)
    assert row["eligibility_result"] == "ELIGIBLE"
    assert row["eligibility_reason_codes"] == f"PASSED_{PROFILE_VERSION}"


def test_profile_on_executes_liquid_v1_when_materialized_flag_is_absent():
    store = UniverseStore([
        {
            "date": date(2020, 1, 1),
            "security_id": "PASS",
            "active": True,
            "instrument_type": "ORDINARY_EQUITY",
            "trading_status": "ACTIVE_TRADING",
            "research_identity_ok": True,
            "price_adjustment_ok": True,
            "price": 25.0,
            "listing_age_sessions": 300,
            "positive_volume_days_60": 40,
            "median_traded_value_60": 5_000_000,
        },
        {
            "date": date(2020, 1, 1),
            "security_id": "FAIL",
            "active": True,
            "instrument_type": "ORDINARY_EQUITY",
            "trading_status": "ACTIVE_TRADING",
            "research_identity_ok": True,
            "price_adjustment_ok": True,
            "price": 25.0,
            "listing_age_sessions": 300,
            "positive_volume_days_60": 39,
            "median_traded_value_60": 5_000_000,
        },
    ])
    assert [row["security_id"] for row in store.profile_on("2020-01-01", PROFILE_VERSION)] == ["PASS"]


def test_profile_on_fails_closed_when_identity_or_status_fields_are_missing():
    store = UniverseStore([
        {
            "date": date(2020, 1, 1),
            "security_id": "MISSING_STATUS",
            "active": True,
            "instrument_type": "ORDINARY_EQUITY",
            "research_identity_ok": True,
            "price_adjustment_ok": True,
            "price": 25.0,
            "listing_age_sessions": 300,
            "positive_volume_days_60": 40,
            "median_traded_value_60": 5_000_000,
        },
        {
            "date": date(2020, 1, 1),
            "security_id": "MISSING_IDENTITY",
            "active": True,
            "instrument_type": "ORDINARY_EQUITY",
            "trading_status": "ACTIVE_TRADING",
            "price_adjustment_ok": True,
            "price": 25.0,
            "listing_age_sessions": 300,
            "positive_volume_days_60": 40,
            "median_traded_value_60": 5_000_000,
        },
    ])
    assert store.profile_on("2020-01-01", PROFILE_VERSION) == []


def test_ranked_liquid_on_excludes_non_ordinary_or_non_active_status():
    store = UniverseStore([
        {"date": date(2020, 1, 1), "security_id": "ETF", "active": True, "instrument_type": "ETF", "trading_status": LIQUID_V1_DEFINITION["trading_status"], TOP_LIQUIDITY_RANKING_METRIC: 100.0},
        {"date": date(2020, 1, 1), "security_id": "SUSPENDED", "active": True, "instrument_type": LIQUID_V1_DEFINITION["instrument_type"], "trading_status": "SUSPENDED", TOP_LIQUIDITY_RANKING_METRIC: 90.0},
        {"date": date(2020, 1, 1), "security_id": "MISSING_TYPE", "active": True, "trading_status": LIQUID_V1_DEFINITION["trading_status"], TOP_LIQUIDITY_RANKING_METRIC: 85.0},
        {"date": date(2020, 1, 1), "security_id": "MISSING_STATUS", "active": True, "instrument_type": LIQUID_V1_DEFINITION["instrument_type"], TOP_LIQUIDITY_RANKING_METRIC: 82.0},
        {"date": date(2020, 1, 1), "security_id": "EQUITY", "active": True, "instrument_type": LIQUID_V1_DEFINITION["instrument_type"], "trading_status": LIQUID_V1_DEFINITION["trading_status"], TOP_LIQUIDITY_RANKING_METRIC: 80.0},
    ])
    assert [row["security_id"] for row in store.ranked_liquid_on("2020-01-01", 10)] == ["EQUITY"]


def test_parquet_ranked_liquid_on_excludes_non_ordinary_or_non_active_status(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    path = tmp_path / "active_universe_daily.parquet"
    pq.write_table(
        pa.table(
            {
                "date": ["2020-01-01", "2020-01-01", "2020-01-01"],
                "security_id": ["ETF", "SUSPENDED", "EQUITY"],
                "active": [True, True, True],
                "instrument_type": ["ETF", LIQUID_V1_DEFINITION["instrument_type"], LIQUID_V1_DEFINITION["instrument_type"]],
                "trading_status": [LIQUID_V1_DEFINITION["trading_status"], "SUSPENDED", LIQUID_V1_DEFINITION["trading_status"]],
                TOP_LIQUIDITY_RANKING_METRIC: [100.0, 90.0, 80.0],
            }
        ),
        path,
    )
    store = ParquetUniverseStore(path)
    assert [row["security_id"] for row in store.ranked_liquid_on("2020-01-01", 10)] == ["EQUITY"]


def test_parquet_profile_on_executes_liquid_v1_when_materialized_flag_is_absent(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    path = tmp_path / "research_universe_monthly.parquet"
    pq.write_table(
        pa.table(
            {
                "date": ["2020-01-01", "2020-01-01"],
                "security_id": ["PASS", "FAIL"],
                "active": [True, True],
                "instrument_type": ["ORDINARY_EQUITY", "ORDINARY_EQUITY"],
                "trading_status": ["ACTIVE_TRADING", "ACTIVE_TRADING"],
                "research_identity_ok": [True, True],
                "price_adjustment_ok": [True, True],
                "price": [25.0, 25.0],
                "listing_age_sessions": [300, 300],
                "positive_volume_days_60": [40, 39],
                "median_traded_value_60": [5_000_000, 5_000_000],
            }
        ),
        path,
    )
    store = ParquetUniverseStore(path)
    assert [row["security_id"] for row in store.profile_on("2020-01-01", PROFILE_VERSION)] == ["PASS"]


def test_parquet_profile_on_reads_date_typed_monthly_snapshot(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    path = tmp_path / "research_universe_monthly.parquet"
    pq.write_table(
        pa.table(
            {
                "date": [date(2020, 1, 1)],
                "security_id": ["PASS"],
                "active": [True],
                "NSE_BROAD_LIQUID_PIT_V1_eligible": [True],
            }
        ),
        path,
    )
    store = ParquetUniverseStore(path)
    assert [row["security_id"] for row in store.profile_on("2020-01-01", PROFILE_VERSION)] == ["PASS"]


def test_calendar_returns_only_official_sessions():
    store = CalendarStore([{"date": "2020-01-02", "session_evidence": "OFFICIAL_NSE_MARKET_DATA"}, {"date": "2020-01-03", "session_evidence": "OFFICIAL_NSE_MARKET_DATA"}])
    assert [row["date"].isoformat() for row in store.sessions_between("2020-01-01", "2020-01-05")] == ["2020-01-02", "2020-01-03"]
