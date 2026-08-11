import json
from datetime import date

import pytest

from india_active_universe.api import CalendarStore, CompanyNameHistoryStore, CoverageError, DataPlatform, IsinHistoryStore, ParquetUniverseStore, PriceStore, SecurityMaster, StatusStore, TerminalEventStore, UniverseStore
from india_active_universe.identity import apply_manual_overrides, build_identity_rows, load_manual_overrides
from india_active_universe.models import DailyObservation
from india_active_universe.pipeline import build_active_snapshot, classify_instrument_type, discover_securities
from india_active_universe.profiles import (
    ACTIVE_DEFINITION,
    ACTIVE_UNIVERSE_ARTIFACT,
    CANDIDATE_MONTHLY_SNAPSHOT_START,
    CANDIDATE_FEATURE_READINESS_POLICY,
    CANDIDATE_PIT_UNIVERSE_INTERVAL_TYPE,
    CANDIDATE_REFINED_BOUNDARY_SCAN_METHOD,
    CANDIDATE_PROMOTION_SUMMARY_FIELDS,
    CANDIDATE_RESEARCH_START_DATES,
    COMPONENT_QUALITY,
    CANDIDATE_GATE_PASS_INTERPRETATION,
    CANDIDATE_NOT_READY_INTERPRETATION,
    DATA_RELEASE_MANIFEST_ARTIFACT,
    DATASET_QUALITY_TIER,
    EXECUTION_POLICY,
    FEATURE_READINESS_WINDOWS,
    FEATURE_WARMUP_STATUS,
    LIQUIDITY_ARTIFACT,
    LIQUID_V1_DEFINITION,
    PRIORITY_SCOPE,
    PROFILE_ID,
    PROFILE_VERSION,
    PARSER_VERSIONS,
    RAW_EXECUTION_PRICE_ARTIFACT,
    RECOMMENDED_SIGNAL_PRICE_SERIES,
    RESEARCH_EXPLORATORY_STATUS,
    RESEARCH_HIGH_CONFIDENCE_STATUS,
    RESEARCH_RELEASE_MANIFEST_ARTIFACT,
    RESEARCH_MANIFEST_ARTIFACTS,
    RESEARCH_MONTHLY_SNAPSHOT_START,
    RESEARCH_UNIVERSE_MONTHLY_ARTIFACT,
    RESEARCH_START_DATE,
    REQUIRED_QUALITY_THRESHOLD,
    SIGNAL_POLICY,
    SOURCE_BUILD_MODE,
    SOURCE_MANIFEST_ARTIFACT,
    SOURCE_OBSERVED_START_DATE,
    SECURITY_MASTER_ARTIFACT,
    TARGET_RELEASE_ID,
    TERMINAL_VALUE_POLICY,
    TERMINAL_VALUE_POLICY_REQUIREMENT,
    TOP_LIQUIDITY_RANKING_METRIC,
)
from scripts.build_completion_audit import EXPECTED_CANDIDATE_HARD_FAILURE_KEYS, EXPECTED_INVARIANT_VALIDATION_METRICS, REQUIRED, REQUIRED_RESEARCH_REPORTS, candidate_manifest_audit_consistency_failures, candidate_promotion_audit_summary, data_manifest_contract_failures, invariant_validation_summary, research_manifest_contract_failures
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


def test_source_start_identity_rows_are_left_censored_not_ipos():
    identities = build_identity_rows([
        {"exchange": "NSE", "symbol": "OLDCO", "series": "EQ", "first_seen": date(2006, 1, 2), "last_seen": date(2008, 1, 1), "candidate_isin": None, "company_name": "OLD CO", "instrument_type": "ORDINARY_EQUITY"},
        {"exchange": "NSE", "symbol": "NEWCO", "series": "EQ", "first_seen": date(2007, 1, 2), "last_seen": date(2008, 1, 1), "candidate_isin": None, "company_name": "NEW CO", "instrument_type": "ORDINARY_EQUITY"},
    ])
    by_symbol = {row["symbol"]: row for row in identities}

    assert by_symbol["OLDCO"]["listing_history_left_censored"] is True
    assert by_symbol["OLDCO"]["listing_age_sessions_quality"] == "LISTING_HISTORY_LEFT_CENSORED"
    assert by_symbol["OLDCO"]["listing_date_quality"] == "UNKNOWN_LEFT_CENSORED"
    assert by_symbol["NEWCO"]["listing_history_left_censored"] is False
    assert by_symbol["NEWCO"]["listing_age_sessions_quality"] == "FIRST_OBSERVED_TRADE_DATE"


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


def test_platform_research_quality_is_interval_aware():
    platform = DataPlatform()
    platform.coverage_start = date(2006, 1, 2)
    platform.coverage_end = date(2026, 8, 10)
    platform.warmup_coverage = {"earliest_fully_warmed_date": "2007-03-15"}
    platform.research_quality_intervals = [
        {"start": "2013-01-01", "end": "2026-08-10", "status": RESEARCH_HIGH_CONFIDENCE_STATUS}
    ]

    assert platform.research_quality_on("2006-06-30") == FEATURE_WARMUP_STATUS
    assert platform.research_quality_on("2008-01-31") == RESEARCH_EXPLORATORY_STATUS
    assert platform.research_quality_on("2018-03-28") == RESEARCH_HIGH_CONFIDENCE_STATUS
    with pytest.raises(CoverageError):
        platform.research_quality_on("2005-12-30")


def test_platform_feature_readiness_uses_prior_official_sessions():
    sessions = [{"date": f"2020-01-{day:02d}"} for day in range(1, 31)]
    platform = DataPlatform()
    platform.coverage_start = date(2020, 1, 1)
    platform.calendar = CalendarStore(sessions)

    readiness = platform.feature_readiness("2020-01-25")

    assert readiness["prior_official_sessions"] == 24
    assert readiness["ready"]["liquidity_20"] is True
    assert readiness["ready"]["liquidity_60"] is False
    assert readiness["all_ready"] is False


def test_platform_exposes_manifest_warmup_boundaries():
    platform = DataPlatform()
    platform.warmup_coverage = {
        "feature_ready_dates": {
            "liquidity_60": "2006-03-29",
            "model_arena_handoff_history": "2007-03-15",
        },
        "earliest_fully_warmed_date": "2007-03-15",
    }

    assert platform.earliest_feature_ready_date("liquidity_60") == date(2006, 3, 29)
    assert platform.earliest_feature_ready_date("standard_research_252") is None
    assert platform.earliest_fully_warmed_date() == date(2007, 3, 15)
    with pytest.raises(ValueError, match="Unknown feature readiness window"):
        platform.earliest_feature_ready_date("not_a_feature")


def test_platform_exposes_candidate_promotion_decisions():
    platform = DataPlatform()
    platform.candidate_promotion_decisions = [
        {
            "candidate_start": "2009-01-01",
            "candidate_audit_status": "FAIL",
            "decision_window_gate": "PASS",
            "warmup_gate": "PASS",
            "feature_readiness": {"feature_warmup_not_ready": False},
            "refined_earliest_passing_snapshot": "2009-01-30",
            "promotion_interpretation": CANDIDATE_NOT_READY_INTERPRETATION,
        }
    ]
    platform.earliest_candidate_gate_pass_start = date(2009, 1, 1)
    platform._refined_earliest_candidate_gate_pass_boundary = date(2009, 1, 30)

    decision = platform.candidate_promotion_decision("2009-01-01")

    assert decision["warmup_gate"] == "PASS"
    assert platform.earliest_candidate_gate_pass_date() == date(2009, 1, 1)
    assert platform.candidate_promotion_summary()["recorded_earliest_candidate_gate_pass_start"] == "2009-01-01"
    assert platform.candidate_promotion_summary()["earliest_candidate_gate_pass_start"] is None
    assert platform.candidate_promotion_summary()["recorded_matches_derived_earliest_candidate_gate_pass_start"] is False
    assert platform.candidate_promotion_summary()["refined_earliest_candidate_gate_pass_boundary"] == "2009-01-30"
    assert platform.candidate_promotion_summary()["recorded_matches_derived_refined_earliest_candidate_gate_pass_boundary"] is True
    assert platform.candidate_promotion_summary()["candidate_gate_pass_start_dates"] == []
    assert platform.candidate_promotion_summary()["candidate_research_ready_start_dates"] == []
    assert platform.candidate_pit_universe_ready("2009-01-29") is False
    assert platform.candidate_pit_universe_ready("2009-01-30") is True
    platform.coverage_end = date(2009, 2, 28)
    assert platform.candidate_pit_universe_ready("2009-03-01") is False
    assert platform.candidate_promotion_status()[0]["candidate_start"] == "2009-01-01"
    with pytest.raises(LookupError):
        platform.candidate_promotion_decision("2007-01-01")


def test_platform_exposes_candidate_gate_pass_start_dates():
    platform = DataPlatform()
    platform.candidate_promotion_decisions = [
        {
            "candidate_start": "2011-01-01",
            "candidate_audit_status": "PASS",
        },
        {
            "candidate_start": "2010-01-01",
            "candidate_audit_status": "PASS",
            "decision_window_gate": "PASS",
            "warmup_gate": "PASS",
            "feature_readiness": {"feature_warmup_not_ready": False},
            "session_liquidity_gate": "PASS",
            "identity_gate": "PASS",
            "price_action_gate": "PASS",
            "instrument_gate": "PASS",
            "status_gate": "PASS",
            "promotion_interpretation": CANDIDATE_GATE_PASS_INTERPRETATION,
        },
        {
            "candidate_start": "2007-01-01",
            "candidate_audit_status": "PASS",
            "decision_window_gate": "PASS",
            "warmup_gate": "PASS",
            "feature_readiness": {"feature_warmup_not_ready": False},
            "session_liquidity_gate": "PASS",
            "identity_gate": "PASS",
            "price_action_gate": "PASS",
            "instrument_gate": "PASS",
            "status_gate": "PASS",
            "promotion_interpretation": CANDIDATE_GATE_PASS_INTERPRETATION,
        },
        {
            "candidate_start": "2009-01-01",
            "candidate_audit_status": "PASS",
            "decision_window_gate": "PASS",
            "warmup_gate": "PASS",
            "feature_readiness": {"feature_warmup_not_ready": False},
            "session_liquidity_gate": "PASS",
            "identity_gate": "PASS",
            "price_action_gate": "PASS",
            "instrument_gate": "PASS",
            "status_gate": "PASS",
            "promotion_interpretation": CANDIDATE_GATE_PASS_INTERPRETATION,
        },
        {
            "candidate_start": "2006-01-01",
            "candidate_audit_status": "FAIL",
            "decision_window_gate": "PASS",
            "warmup_gate": "PASS",
            "feature_readiness": {"feature_warmup_not_ready": False},
            "session_liquidity_gate": "PASS",
            "identity_gate": "FAIL",
            "price_action_gate": "PASS",
            "instrument_gate": "PASS",
            "status_gate": "PASS",
            "promotion_interpretation": CANDIDATE_NOT_READY_INTERPRETATION,
        },
    ]

    assert platform.candidate_gate_pass_start_dates() == [date(2007, 1, 1), date(2009, 1, 1)]
    assert platform.candidate_promotion_summary()["earliest_candidate_gate_pass_start"] == "2007-01-01"
    assert platform.candidate_promotion_summary()["recorded_matches_derived_earliest_candidate_gate_pass_start"] is False
    assert platform.candidate_gate_pass_ready("2009-01-01") is True
    assert platform.candidate_gate_pass_ready("2006-01-01") is False
    platform.coverage_start = date(2006, 1, 2)
    platform.coverage_end = date(2026, 8, 10)
    assert platform.candidate_research_ready("2009-01-01") is False
    assert platform.candidate_research_ready_start_dates() == []
    platform.research_quality_intervals = [
        {"start": "2009-01-01", "end": "2009-12-31", "status": RESEARCH_HIGH_CONFIDENCE_STATUS}
    ]
    assert platform.candidate_research_ready("2009-01-01") is True
    assert platform.candidate_research_ready_start_dates() == [date(2009, 1, 1)]
    with pytest.raises(ValueError, match="candidate_start is not configured"):
        platform.candidate_gate_pass_ready("2010-01-01")
    with pytest.raises(ValueError, match="candidate_start is not configured"):
        platform.candidate_research_ready("2010-01-01")


def test_platform_exposes_machine_readable_candidate_promotion_contract():
    from india_active_universe import (
        CANDIDATE_AUDIT_STATUS_VALUES,
        CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS,
        CANDIDATE_DECISION_GATE_KEYS,
        CANDIDATE_DECISION_GATE_VALUES,
        CANDIDATE_DECISION_REQUIRED_FIELDS,
        CANDIDATE_FAIL_VALUE,
        CANDIDATE_FEATURE_READINESS_POLICY,
        CANDIDATE_GATE_PASS_INTERPRETATION,
        CANDIDATE_HARD_FAILURE_KEYS,
        CANDIDATE_NOT_RECORDED_VALUE,
        CANDIDATE_NUMERIC_HARD_FAILURE_KEYS,
        CANDIDATE_PASS_VALUE,
        CANDIDATE_PIT_UNIVERSE_INTERVAL_TYPE,
        CANDIDATE_PROMOTION_API_METHODS,
        CANDIDATE_PROMOTION_INTERPRETATION_VALUES,
        CANDIDATE_PROMOTION_SUMMARY_FIELDS,
        CANDIDATE_REFINED_BOUNDARY_SCAN_METHOD,
        CANDIDATE_RESEARCH_START_DATES,
    )

    contract = DataPlatform().candidate_promotion_contract()

    assert tuple(contract["candidate_research_start_dates"]) == CANDIDATE_RESEARCH_START_DATES
    assert tuple(contract["candidate_promotion_api_methods"]) == CANDIDATE_PROMOTION_API_METHODS
    assert "candidate_pit_universe_ready" in contract["candidate_promotion_api_methods"]
    assert tuple(contract["candidate_decision_required_fields"]) == CANDIDATE_DECISION_REQUIRED_FIELDS
    assert tuple(contract["candidate_promotion_summary_fields"]) == CANDIDATE_PROMOTION_SUMMARY_FIELDS
    assert tuple(contract["candidate_decision_gate_keys"]) == CANDIDATE_DECISION_GATE_KEYS
    assert tuple(contract["candidate_hard_failure_keys"]) == CANDIDATE_HARD_FAILURE_KEYS
    assert tuple(contract["candidate_boolean_hard_failure_keys"]) == CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS
    assert tuple(contract["candidate_numeric_hard_failure_keys"]) == CANDIDATE_NUMERIC_HARD_FAILURE_KEYS
    assert tuple(contract["candidate_audit_status_values"]) == CANDIDATE_AUDIT_STATUS_VALUES
    assert tuple(contract["candidate_decision_gate_values"]) == CANDIDATE_DECISION_GATE_VALUES
    assert tuple(contract["candidate_promotion_interpretation_values"]) == CANDIDATE_PROMOTION_INTERPRETATION_VALUES
    assert contract["candidate_pass_value"] == CANDIDATE_PASS_VALUE
    assert contract["candidate_fail_value"] == CANDIDATE_FAIL_VALUE
    assert contract["candidate_refined_boundary_scan_method"] == CANDIDATE_REFINED_BOUNDARY_SCAN_METHOD
    assert contract["candidate_pit_universe_interval_type"] == CANDIDATE_PIT_UNIVERSE_INTERVAL_TYPE
    assert contract["candidate_feature_readiness_policy"] == CANDIDATE_FEATURE_READINESS_POLICY
    assert contract["candidate_not_recorded_value"] == CANDIDATE_NOT_RECORDED_VALUE
    assert contract["candidate_gate_pass_interpretation"] == CANDIDATE_GATE_PASS_INTERPRETATION


def test_candidate_promotion_summary_matches_published_field_contract():
    summary = DataPlatform().candidate_promotion_summary()

    assert tuple(summary.keys()) == CANDIDATE_PROMOTION_SUMMARY_FIELDS


def test_candidate_readiness_cli_prints_candidate_start_status(monkeypatch, capsys):
    from india_active_universe import cli
    from india_active_universe import api

    class FakePlatform:
        quality_tier = "DATASET_EXPLORATORY"
        coverage_start = date(2006, 1, 2)
        coverage_end = date(2026, 8, 10)
        verified_start = date(2013, 1, 1)
        verified_end = date(2026, 8, 10)

        @classmethod
        def from_release(cls, release, *, strict=False):
            assert str(release).endswith("releases/india_equity_data_test")
            assert strict is False
            return cls()

        def candidate_promotion_decision(self, candidate_start):
            return {
                "candidate_start": candidate_start,
                "candidate_audit_status": "FAIL",
                "feature_readiness": {"feature_warmup_not_ready": True},
                "refined_earliest_passing_snapshot": "2006-07-31",
            }

        def refined_earliest_candidate_gate_pass_boundary(self):
            return date(2006, 7, 31)

        def candidate_gate_pass_ready(self, candidate_start):
            return False

        def candidate_pit_universe_ready(self, as_of_date):
            return False

        def research_quality_on(self, candidate_start):
            return RESEARCH_EXPLORATORY_STATUS

        def candidate_research_ready(self, candidate_start):
            return False

    monkeypatch.setattr(api, "DataPlatform", FakePlatform)
    monkeypatch.setattr(
        "sys.argv",
        [
            "india-equity-data",
            "candidate-readiness",
            "--root",
            "/tmp/project",
            "--release-id",
            "india_equity_data_test",
            "--candidate-start",
            "2006-01-01",
        ],
    )

    cli.main()

    output = json.loads(capsys.readouterr().out)
    assert output["release_id"] == "india_equity_data_test"
    assert output["quality_tier"] == "DATASET_EXPLORATORY"
    assert output["coverage_start"] == "2006-01-02"
    assert output["verified_start"] == "2013-01-01"
    assert output["candidate_start"] == "2006-01-01"
    assert output["candidate_decision"]["candidate_audit_status"] == "FAIL"
    assert output["candidate_feature_readiness"] == {"feature_warmup_not_ready": True}
    assert output["candidate_refined_earliest_passing_snapshot"] == "2006-07-31"
    assert output["refined_earliest_candidate_gate_pass_boundary"] == "2006-07-31"
    assert output["candidate_pit_universe_ready"] is False
    assert output["candidate_gate_pass_ready"] is False
    assert output["research_quality_status"] == RESEARCH_EXPLORATORY_STATUS
    assert output["candidate_research_ready"] is False


def test_candidate_readiness_cli_prints_candidate_summary(monkeypatch, capsys):
    from india_active_universe import cli
    from india_active_universe import api

    class FakePlatform:
        @classmethod
        def from_release(cls, release, *, strict=False):
            assert str(release).endswith("releases/india_equity_data_test")
            assert strict is False
            return cls()

        def candidate_promotion_summary(self):
            return {
                "recorded_earliest_candidate_gate_pass_start": None,
                "earliest_candidate_gate_pass_start": None,
                "recorded_matches_derived_earliest_candidate_gate_pass_start": True,
                "candidate_gate_pass_start_dates": [],
                "candidate_research_ready_start_dates": [],
                "recorded_refined_earliest_candidate_gate_pass_boundary": None,
                "refined_earliest_candidate_gate_pass_boundary": None,
                "recorded_matches_derived_refined_earliest_candidate_gate_pass_boundary": True,
                "candidate_recommended_pit_universe_interval": {
                    "status": "NO_REFINED_BOUNDARY",
                    "start": None,
                    "end": None,
                    "profile": "NSE_BROAD_LIQUID_PIT_V1",
                    "profile_version": "LIQUID_V1",
                    "boundary_scan_method": CANDIDATE_REFINED_BOUNDARY_SCAN_METHOD,
                    "promotion_status": "NOT_PROMOTED_UNLESS_PRESENT_IN_RESEARCH_QUALITY_INTERVALS",
                    "interval_type": CANDIDATE_PIT_UNIVERSE_INTERVAL_TYPE,
                    "feature_readiness_policy": CANDIDATE_FEATURE_READINESS_POLICY,
                },
                "candidate_recommended_research_interval": {
                    "status": "NO_REFINED_BOUNDARY",
                    "start": None,
                    "end": None,
                    "profile": "NSE_BROAD_LIQUID_PIT_V1",
                    "profile_version": "LIQUID_V1",
                    "boundary_scan_method": CANDIDATE_REFINED_BOUNDARY_SCAN_METHOD,
                    "promotion_status": "NOT_PROMOTED_UNLESS_PRESENT_IN_RESEARCH_QUALITY_INTERVALS",
                },
                "candidate_promotion_decisions": [],
            }

    monkeypatch.setattr(api, "DataPlatform", FakePlatform)
    monkeypatch.setattr(
        "sys.argv",
        [
            "india-equity-data",
            "candidate-readiness",
            "--root",
            "/tmp/project",
            "--release-id",
            "india_equity_data_test",
        ],
    )

    cli.main()

    output = json.loads(capsys.readouterr().out)
    assert output["release_id"] == "india_equity_data_test"
    assert output["quality_tier"] == "DATASET_EXPLORATORY"
    assert output["coverage_start"] == "2006-01-02"
    assert output["verified_start"] == "2013-01-01"
    assert tuple(output["candidate_promotion_summary"].keys()) == CANDIDATE_PROMOTION_SUMMARY_FIELDS
    assert output["candidate_promotion_summary"]["candidate_gate_pass_start_dates"] == []


def test_candidate_promotion_loader_rejects_duplicate_candidate_starts():
    from india_active_universe.api import _normalize_candidate_promotion_decisions
    from india_active_universe.profiles import (
        CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS,
        CANDIDATE_NUMERIC_HARD_FAILURE_KEYS,
    )

    hard_failures = {
        **{key: False for key in CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS},
        **{key: 0 for key in CANDIDATE_NUMERIC_HARD_FAILURE_KEYS},
    }
    row = {
        "candidate_start": "2009-01-01",
        "candidate_audit_status": "FAIL",
        "decision_window_gate": "PASS",
        "warmup_gate": "PASS",
        "feature_readiness": {"feature_warmup_not_ready": False},
        "session_liquidity_gate": "PASS",
        "identity_gate": "FAIL",
        "price_action_gate": "PASS",
        "instrument_gate": "PASS",
        "status_gate": "PASS",
        "hard_failures": {**hard_failures, "identity_failures": 1},
        "promotion_interpretation": CANDIDATE_NOT_READY_INTERPRETATION,
    }

    with pytest.raises(ValueError, match="duplicate candidate_start"):
        _normalize_candidate_promotion_decisions([row, row])


def test_candidate_promotion_loader_rejects_partial_candidate_start_sets():
    from india_active_universe.api import _normalize_candidate_promotion_decisions
    from india_active_universe.profiles import (
        CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS,
        CANDIDATE_NUMERIC_HARD_FAILURE_KEYS,
    )

    hard_failures = {
        **{key: False for key in CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS},
        **{key: 0 for key in CANDIDATE_NUMERIC_HARD_FAILURE_KEYS},
    }
    row = {
        "candidate_start": "2009-01-01",
        "candidate_audit_status": "FAIL",
        "decision_window_gate": "PASS",
        "warmup_gate": "PASS",
        "feature_readiness": {"feature_warmup_not_ready": False},
        "session_liquidity_gate": "PASS",
        "identity_gate": "FAIL",
        "price_action_gate": "PASS",
        "instrument_gate": "PASS",
        "status_gate": "PASS",
        "hard_failures": {**hard_failures, "identity_failures": 1},
        "promotion_interpretation": CANDIDATE_NOT_READY_INTERPRETATION,
    }

    assert _normalize_candidate_promotion_decisions([]) == []
    with pytest.raises(ValueError, match="missing configured candidate starts"):
        _normalize_candidate_promotion_decisions([row])


def test_candidate_promotion_loader_returns_configured_candidate_order():
    from india_active_universe.api import _normalize_candidate_promotion_decisions
    from india_active_universe.profiles import (
        CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS,
        CANDIDATE_NUMERIC_HARD_FAILURE_KEYS,
    )

    hard_failures = {
        **{key: False for key in CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS},
        **{key: 0 for key in CANDIDATE_NUMERIC_HARD_FAILURE_KEYS},
        "identity_failures": 1,
    }
    row_template = {
        "candidate_audit_status": "FAIL",
        "decision_window_gate": "PASS",
        "warmup_gate": "PASS",
        "feature_readiness": {"feature_warmup_not_ready": False},
        "session_liquidity_gate": "PASS",
        "identity_gate": "FAIL",
        "price_action_gate": "PASS",
        "instrument_gate": "PASS",
        "status_gate": "PASS",
        "hard_failures": hard_failures,
        "promotion_interpretation": CANDIDATE_NOT_READY_INTERPRETATION,
    }
    rows = [
        {**row_template, "candidate_start": candidate_start}
        for candidate_start in reversed(CANDIDATE_RESEARCH_START_DATES)
    ]

    normalized = _normalize_candidate_promotion_decisions(rows)

    assert [row["candidate_start"] for row in normalized] == list(CANDIDATE_RESEARCH_START_DATES)


def test_candidate_promotion_loader_rejects_invalid_candidate_values():
    from india_active_universe.api import _normalize_candidate_promotion_decisions
    from india_active_universe.profiles import (
        CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS,
        CANDIDATE_NUMERIC_HARD_FAILURE_KEYS,
    )

    hard_failures = {
        **{key: False for key in CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS},
        **{key: 0 for key in CANDIDATE_NUMERIC_HARD_FAILURE_KEYS},
    }
    row = {
        "candidate_start": "2009-01-01",
        "candidate_audit_status": "FAIL",
        "decision_window_gate": "PASS",
        "warmup_gate": "PASS",
        "feature_readiness": {"feature_warmup_not_ready": False},
        "session_liquidity_gate": "PASS",
        "identity_gate": "FAIL",
        "price_action_gate": "PASS",
        "instrument_gate": "PASS",
        "status_gate": "PASS",
        "hard_failures": {**hard_failures, "identity_failures": 1},
        "promotion_interpretation": CANDIDATE_NOT_READY_INTERPRETATION,
    }

    invalid_cases = (
        ({**row, "candidate_start": "2010-01-01"}, "candidate_start is not configured"),
        ({**row, "candidate_audit_status": "UNKNOWN"}, "candidate_audit_status is invalid"),
        ({**row, "identity_gate": "UNKNOWN"}, "identity_gate is invalid"),
        ({**row, "feature_model_readiness_complete": False}, "feature_model_readiness_complete contradicts feature_readiness"),
        ({**row, "pit_universe_gate_pass": True}, "pit_universe_gate_pass contradicts candidate_audit_status"),
        ({**row, "promotion_interpretation": "UNKNOWN"}, "promotion_interpretation is invalid"),
    )
    for invalid_row, message in invalid_cases:
        with pytest.raises(ValueError, match=message):
            _normalize_candidate_promotion_decisions([invalid_row])


def test_candidate_promotion_loader_rejects_extra_hard_failure_keys():
    from india_active_universe.api import _normalize_candidate_promotion_decisions
    from india_active_universe.profiles import (
        CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS,
        CANDIDATE_NUMERIC_HARD_FAILURE_KEYS,
    )

    hard_failures = {
        **{key: False for key in CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS},
        **{key: 0 for key in CANDIDATE_NUMERIC_HARD_FAILURE_KEYS},
        "identity_failures": 1,
        "unexpected_failure": 1,
    }
    row_template = {
        "candidate_audit_status": "FAIL",
        "decision_window_gate": "PASS",
        "warmup_gate": "PASS",
        "feature_readiness": {"feature_warmup_not_ready": False},
        "session_liquidity_gate": "PASS",
        "identity_gate": "FAIL",
        "price_action_gate": "PASS",
        "instrument_gate": "PASS",
        "status_gate": "PASS",
        "hard_failures": hard_failures,
        "promotion_interpretation": CANDIDATE_NOT_READY_INTERPRETATION,
    }
    rows = [
        {**row_template, "candidate_start": candidate_start}
        for candidate_start in CANDIDATE_RESEARCH_START_DATES
    ]

    with pytest.raises(ValueError, match="unexpected fields"):
        _normalize_candidate_promotion_decisions(rows)


def test_candidate_promotion_loader_rejects_audit_status_hard_failure_contradictions():
    from india_active_universe.api import _normalize_candidate_promotion_decisions
    from india_active_universe.profiles import (
        CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS,
        CANDIDATE_NUMERIC_HARD_FAILURE_KEYS,
    )

    no_failures = {
        **{key: False for key in CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS},
        **{key: 0 for key in CANDIDATE_NUMERIC_HARD_FAILURE_KEYS},
    }
    row = {
        "candidate_start": "2009-01-01",
        "candidate_audit_status": "FAIL",
        "decision_window_gate": "PASS",
        "warmup_gate": "PASS",
        "feature_readiness": {"feature_warmup_not_ready": False},
        "session_liquidity_gate": "PASS",
        "identity_gate": "FAIL",
        "price_action_gate": "PASS",
        "instrument_gate": "PASS",
        "status_gate": "PASS",
        "hard_failures": no_failures,
        "promotion_interpretation": CANDIDATE_NOT_READY_INTERPRETATION,
    }

    with pytest.raises(ValueError, match="FAIL without active hard failures"):
        _normalize_candidate_promotion_decisions([row])

    with pytest.raises(ValueError, match="PASS with active hard failures"):
        _normalize_candidate_promotion_decisions([
            {
                **row,
                "candidate_audit_status": "PASS",
                "identity_gate": "PASS",
                "hard_failures": {**no_failures, "identity_failures": 1},
            }
        ])


def test_candidate_promotion_loader_rejects_gate_pass_interpretation_contradictions():
    from india_active_universe.api import _normalize_candidate_promotion_decisions
    from india_active_universe.profiles import (
        CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS,
        CANDIDATE_NUMERIC_HARD_FAILURE_KEYS,
    )

    no_failures = {
        **{key: False for key in CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS},
        **{key: 0 for key in CANDIDATE_NUMERIC_HARD_FAILURE_KEYS},
    }
    gate_pass_row = {
        "candidate_start": "2009-01-01",
        "candidate_audit_status": "PASS",
        "decision_window_gate": "PASS",
        "warmup_gate": "PASS",
        "feature_readiness": {"feature_warmup_not_ready": False},
        "session_liquidity_gate": "PASS",
        "identity_gate": "PASS",
        "price_action_gate": "PASS",
        "instrument_gate": "PASS",
        "status_gate": "PASS",
        "hard_failures": no_failures,
        "promotion_interpretation": CANDIDATE_GATE_PASS_INTERPRETATION,
    }

    with pytest.raises(ValueError, match="gate-pass interpretation without PASS audit status and all PASS gates"):
        _normalize_candidate_promotion_decisions([
            {
                **gate_pass_row,
                "candidate_audit_status": "FAIL",
                "identity_gate": "FAIL",
                "hard_failures": {**no_failures, "identity_failures": 1},
            }
        ])

    with pytest.raises(ValueError, match="gate-pass but has non-gate-pass interpretation"):
        _normalize_candidate_promotion_decisions([
            {
                **gate_pass_row,
                "promotion_interpretation": CANDIDATE_NOT_READY_INTERPRETATION,
            }
        ])


def test_candidate_promotion_loader_validates_earliest_candidate_gate_pass_start():
    from india_active_universe.api import _normalize_earliest_candidate_gate_pass_start
    from india_active_universe.profiles import (
        CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS,
        CANDIDATE_NUMERIC_HARD_FAILURE_KEYS,
    )

    no_failures = {
        **{key: False for key in CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS},
        **{key: 0 for key in CANDIDATE_NUMERIC_HARD_FAILURE_KEYS},
    }
    gate_pass = {
        "candidate_start": "2009-01-01",
        "candidate_audit_status": "PASS",
        "decision_window_gate": "PASS",
        "warmup_gate": "PASS",
        "feature_readiness": {"feature_warmup_not_ready": False},
        "session_liquidity_gate": "PASS",
        "identity_gate": "PASS",
        "price_action_gate": "PASS",
        "instrument_gate": "PASS",
        "status_gate": "PASS",
        "hard_failures": no_failures,
        "promotion_interpretation": CANDIDATE_GATE_PASS_INTERPRETATION,
    }
    earlier_gate_pass = {**gate_pass, "candidate_start": "2011-01-01"}

    assert _normalize_earliest_candidate_gate_pass_start("2009-01-01", [gate_pass]).isoformat() == "2009-01-01"
    assert _normalize_earliest_candidate_gate_pass_start(None, []) is None
    with pytest.raises(ValueError, match="null despite gate-pass candidate decisions"):
        _normalize_earliest_candidate_gate_pass_start(None, [gate_pass])
    with pytest.raises(ValueError, match="is not configured"):
        _normalize_earliest_candidate_gate_pass_start("2010-01-01", [gate_pass])
    with pytest.raises(ValueError, match="set without gate-pass candidate decisions"):
        _normalize_earliest_candidate_gate_pass_start("2009-01-01", [])
    with pytest.raises(ValueError, match="must be earliest gate-pass candidate"):
        _normalize_earliest_candidate_gate_pass_start("2011-01-01", [earlier_gate_pass, gate_pass])


def test_strict_platform_uses_research_verified_range_for_release(tmp_path):
    import json
    import pyarrow as pa
    import pyarrow.parquet as pq

    release = tmp_path / "india_equity_data_test"
    release.mkdir()
    (release / DATA_RELEASE_MANIFEST_ARTIFACT).write_text(
        json.dumps(
            {
                "coverage": {"observed_start": SOURCE_OBSERVED_START_DATE, "observed_end": "2026-08-10"},
                "verified_start_date": SOURCE_OBSERVED_START_DATE,
                "verified_end_date": "2026-08-10",
                "quality_tier": "DATASET_EXPLORATORY",
            }
        ),
        encoding="utf-8",
    )
    (release / RESEARCH_RELEASE_MANIFEST_ARTIFACT).write_text(
        json.dumps(
            {
                "research_quality": {
                    "status": RESEARCH_HIGH_CONFIDENCE_STATUS,
                    "start": RESEARCH_START_DATE,
                    "end": "2026-08-10",
                },
                "candidate_promotion_decisions": [
                    {
                        "candidate_start": candidate_start,
                        "candidate_audit_status": "FAIL",
                        "decision_window_gate": "PASS",
                        "warmup_gate": "PASS",
                        "feature_readiness": {"feature_warmup_not_ready": False},
                        "session_liquidity_gate": "PASS",
                        "identity_gate": "FAIL",
                        "price_action_gate": "PASS",
                        "instrument_gate": "PASS",

                        "status_gate": "PASS",
                        "hard_failures": {
                            **{key: 0 for key in EXPECTED_CANDIDATE_HARD_FAILURE_KEYS},
                            "not_materialized": False,
                            "candidate_start_snapshot_missing": False,
                            "decision_window_snapshots_missing": False,
                            "identity_failures": 1,
                        },
                        "promotion_interpretation": CANDIDATE_NOT_READY_INTERPRETATION,
                    }
                    for candidate_start in CANDIDATE_RESEARCH_START_DATES
                ],
                "earliest_candidate_gate_pass_start": None,
            }
        ),
        encoding="utf-8",
    )
    pq.write_table(pa.table({"security_id": []}), release / SECURITY_MASTER_ARTIFACT)
    for name in (ACTIVE_UNIVERSE_ARTIFACT, LIQUIDITY_ARTIFACT, RAW_EXECUTION_PRICE_ARTIFACT):
        pq.write_table(pa.table({"date": [], "security_id": []}), release / name)

    platform = DataPlatform.from_release(release, strict=True)
    assert platform.verified_start == date.fromisoformat(RESEARCH_START_DATE)
    assert platform.quality_tier == RESEARCH_HIGH_CONFIDENCE_STATUS
    assert platform.candidate_promotion_decision("2009-01-01")["identity_gate"] == "FAIL"
    with pytest.raises(CoverageError):
        platform.active_on("2012-12-31")


def test_release_loader_rejects_pre_warmup_data_manifest_research_interval(tmp_path):
    import json

    release = tmp_path / "india_equity_data_test"
    release.mkdir()
    (release / DATA_RELEASE_MANIFEST_ARTIFACT).write_text(
        json.dumps(
            {
                "coverage": {"observed_start": SOURCE_OBSERVED_START_DATE, "observed_end": "2026-08-10"},
                "verified_start_date": SOURCE_OBSERVED_START_DATE,
                "verified_end_date": "2026-08-10",
                "quality_tier": "DATASET_EXPLORATORY",
                "warmup_coverage": {"earliest_fully_warmed_date": "2007-03-15"},
                "research_quality_intervals": [
                    {
                        "start": "2007-01-31",
                        "end": "2026-08-10",
                        "status": RESEARCH_HIGH_CONFIDENCE_STATUS,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="data manifest pre-2013 RESEARCH_HIGH_CONFIDENCE interval starts before earliest fully warmed date"):
        DataPlatform.from_release(release, strict=True)


def test_release_loader_rejects_pre_warmup_research_manifest_research_interval(tmp_path):
    import json

    release = tmp_path / "india_equity_data_test"
    release.mkdir()
    (release / DATA_RELEASE_MANIFEST_ARTIFACT).write_text(
        json.dumps(
            {
                "coverage": {"observed_start": SOURCE_OBSERVED_START_DATE, "observed_end": "2026-08-10"},
                "verified_start_date": SOURCE_OBSERVED_START_DATE,
                "verified_end_date": "2026-08-10",
                "quality_tier": "DATASET_EXPLORATORY",
                "warmup_coverage": {"earliest_fully_warmed_date": "2007-03-15"},
                "research_quality_intervals": [
                    {
                        "start": RESEARCH_START_DATE,
                        "end": "2026-08-10",
                        "status": RESEARCH_HIGH_CONFIDENCE_STATUS,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (release / RESEARCH_RELEASE_MANIFEST_ARTIFACT).write_text(
        json.dumps(
            {
                "warmup_coverage": {"earliest_fully_warmed_date": "2007-03-15"},
                "research_quality_intervals": [
                    {
                        "start": "2007-01-31",
                        "end": "2026-08-10",
                        "status": RESEARCH_HIGH_CONFIDENCE_STATUS,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="research manifest pre-2013 RESEARCH_HIGH_CONFIDENCE interval starts before earliest fully warmed date"):
        DataPlatform.from_release(release, strict=True)


def test_release_loader_preserves_data_manifest_candidate_state_when_research_manifest_omits_candidate_fields(tmp_path):
    import json
    import pyarrow as pa
    import pyarrow.parquet as pq

    release = tmp_path / "india_equity_data_test"
    release.mkdir()
    hard_failures = {
        **{key: 0 for key in EXPECTED_CANDIDATE_HARD_FAILURE_KEYS},
        "not_materialized": False,
        "candidate_start_snapshot_missing": False,
        "decision_window_snapshots_missing": False,
        "identity_failures": 1,
    }
    candidate_rows = [
        {
            "candidate_start": candidate_start,
            "candidate_audit_status": "FAIL",
            "decision_window_gate": "PASS",
            "warmup_gate": "PASS",
            "feature_readiness": {"feature_warmup_not_ready": False},
            "session_liquidity_gate": "PASS",
            "identity_gate": "FAIL",
            "price_action_gate": "PASS",
            "instrument_gate": "PASS",
            "status_gate": "PASS",
            "hard_failures": hard_failures,
            "promotion_interpretation": CANDIDATE_NOT_READY_INTERPRETATION,
        }
        for candidate_start in CANDIDATE_RESEARCH_START_DATES
    ]
    (release / DATA_RELEASE_MANIFEST_ARTIFACT).write_text(
        json.dumps(
            {
                "coverage": {"observed_start": SOURCE_OBSERVED_START_DATE, "observed_end": "2026-08-10"},
                "verified_start_date": SOURCE_OBSERVED_START_DATE,
                "verified_end_date": "2026-08-10",
                "quality_tier": "DATASET_EXPLORATORY",
                "candidate_promotion_decisions": candidate_rows,
                "earliest_candidate_gate_pass_start": None,
            }
        ),
        encoding="utf-8",
    )
    (release / RESEARCH_RELEASE_MANIFEST_ARTIFACT).write_text(
        json.dumps(
            {
                "research_quality": {
                    "status": RESEARCH_HIGH_CONFIDENCE_STATUS,
                    "start": RESEARCH_START_DATE,
                    "end": "2026-08-10",
                },
            }
        ),
        encoding="utf-8",
    )
    pq.write_table(pa.table({"security_id": []}), release / SECURITY_MASTER_ARTIFACT)
    for name in (ACTIVE_UNIVERSE_ARTIFACT, LIQUIDITY_ARTIFACT, RAW_EXECUTION_PRICE_ARTIFACT):
        pq.write_table(pa.table({"date": [], "security_id": []}), release / name)

    platform = DataPlatform.from_release(release, strict=True)

    assert platform.candidate_promotion_decision("2006-01-01")["identity_gate"] == "FAIL"
    assert platform.earliest_candidate_gate_pass_date() is None


def test_release_loader_requires_earliest_candidate_when_research_manifest_overrides_candidate_decisions(tmp_path):
    import json

    release = tmp_path / "india_equity_data_test"
    release.mkdir()
    (release / DATA_RELEASE_MANIFEST_ARTIFACT).write_text(
        json.dumps(
            {
                "coverage": {"observed_start": SOURCE_OBSERVED_START_DATE, "observed_end": "2026-08-10"},
                "verified_start_date": SOURCE_OBSERVED_START_DATE,
                "verified_end_date": "2026-08-10",
                "quality_tier": "DATASET_EXPLORATORY",
            }
        ),
        encoding="utf-8",
    )
    (release / RESEARCH_RELEASE_MANIFEST_ARTIFACT).write_text(
        json.dumps({"candidate_promotion_decisions": []}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must be provided together"):
        DataPlatform.from_release(release, strict=True)


def test_release_loader_requires_candidate_decisions_when_research_manifest_overrides_earliest_candidate(tmp_path):
    import json

    release = tmp_path / "india_equity_data_test"
    release.mkdir()
    (release / DATA_RELEASE_MANIFEST_ARTIFACT).write_text(
        json.dumps(
            {
                "coverage": {"observed_start": SOURCE_OBSERVED_START_DATE, "observed_end": "2026-08-10"},
                "verified_start_date": SOURCE_OBSERVED_START_DATE,
                "verified_end_date": "2026-08-10",
                "quality_tier": "DATASET_EXPLORATORY",
            }
        ),
        encoding="utf-8",
    )
    (release / RESEARCH_RELEASE_MANIFEST_ARTIFACT).write_text(
        json.dumps({"earliest_candidate_gate_pass_start": None}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must be provided together"):
        DataPlatform.from_release(release, strict=True)


def test_release_loader_requires_earliest_candidate_when_data_manifest_publishes_candidate_decisions(tmp_path):
    import json

    release = tmp_path / "india_equity_data_test"
    release.mkdir()
    (release / DATA_RELEASE_MANIFEST_ARTIFACT).write_text(
        json.dumps(
            {
                "coverage": {"observed_start": SOURCE_OBSERVED_START_DATE, "observed_end": "2026-08-10"},
                "verified_start_date": SOURCE_OBSERVED_START_DATE,
                "verified_end_date": "2026-08-10",
                "quality_tier": "DATASET_EXPLORATORY",
                "candidate_promotion_decisions": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must be provided together"):
        DataPlatform.from_release(release, strict=True)


def test_release_loader_requires_candidate_decisions_when_data_manifest_publishes_earliest_candidate(tmp_path):
    import json

    release = tmp_path / "india_equity_data_test"
    release.mkdir()
    (release / DATA_RELEASE_MANIFEST_ARTIFACT).write_text(
        json.dumps(
            {
                "coverage": {"observed_start": SOURCE_OBSERVED_START_DATE, "observed_end": "2026-08-10"},
                "verified_start_date": SOURCE_OBSERVED_START_DATE,
                "verified_end_date": "2026-08-10",
                "quality_tier": "DATASET_EXPLORATORY",
                "earliest_candidate_gate_pass_start": None,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must be provided together"):
        DataPlatform.from_release(release, strict=True)


def test_release_loader_requires_refined_boundary_when_data_manifest_candidate_rows_publish_refined_snapshots(tmp_path):
    import json

    release = tmp_path / "india_equity_data_test"
    release.mkdir()
    candidate_decisions = [
        {
            "candidate_start": candidate_start,
            "candidate_audit_status": "FAIL",
            "decision_window_gate": "PASS",
            "warmup_gate": "PASS",
            "feature_readiness": {"feature_warmup_not_ready": False},
            "session_liquidity_gate": "PASS",
            "identity_gate": "FAIL",
            "price_action_gate": "PASS",
            "instrument_gate": "PASS",
            "status_gate": "PASS",
            "refined_earliest_passing_snapshot": None,
            "hard_failures": {
                **{key: 0 for key in EXPECTED_CANDIDATE_HARD_FAILURE_KEYS},
                "not_materialized": False,
                "candidate_start_snapshot_missing": False,
                "decision_window_snapshots_missing": False,
                "identity_failures": 1,
            },
            "promotion_interpretation": CANDIDATE_NOT_READY_INTERPRETATION,
        }
        for candidate_start in CANDIDATE_RESEARCH_START_DATES
    ]
    (release / DATA_RELEASE_MANIFEST_ARTIFACT).write_text(
        json.dumps(
            {
                "coverage": {"observed_start": SOURCE_OBSERVED_START_DATE, "observed_end": "2026-08-10"},
                "verified_start_date": SOURCE_OBSERVED_START_DATE,
                "verified_end_date": "2026-08-10",
                "quality_tier": "DATASET_EXPLORATORY",
                "candidate_promotion_decisions": candidate_decisions,
                "earliest_candidate_gate_pass_start": None,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="refined_earliest_candidate_gate_pass_boundary must be provided"):
        DataPlatform.from_release(release, strict=True)


def test_release_loader_requires_refined_boundary_when_research_manifest_candidate_rows_publish_refined_snapshots(tmp_path):
    import json

    release = tmp_path / "india_equity_data_test"
    release.mkdir()
    (release / DATA_RELEASE_MANIFEST_ARTIFACT).write_text(
        json.dumps(
            {
                "coverage": {"observed_start": SOURCE_OBSERVED_START_DATE, "observed_end": "2026-08-10"},
                "verified_start_date": SOURCE_OBSERVED_START_DATE,
                "verified_end_date": "2026-08-10",
                "quality_tier": "DATASET_EXPLORATORY",
            }
        ),
        encoding="utf-8",
    )
    candidate_decisions = [
        {
            "candidate_start": candidate_start,
            "candidate_audit_status": "FAIL",
            "decision_window_gate": "PASS",
            "warmup_gate": "PASS",
            "feature_readiness": {"feature_warmup_not_ready": False},
            "session_liquidity_gate": "PASS",
            "identity_gate": "FAIL",
            "price_action_gate": "PASS",
            "instrument_gate": "PASS",
            "status_gate": "PASS",
            "refined_earliest_passing_snapshot": None,
            "hard_failures": {
                **{key: 0 for key in EXPECTED_CANDIDATE_HARD_FAILURE_KEYS},
                "not_materialized": False,
                "candidate_start_snapshot_missing": False,
                "decision_window_snapshots_missing": False,
                "identity_failures": 1,
            },
            "promotion_interpretation": CANDIDATE_NOT_READY_INTERPRETATION,
        }
        for candidate_start in CANDIDATE_RESEARCH_START_DATES
    ]
    (release / RESEARCH_RELEASE_MANIFEST_ARTIFACT).write_text(
        json.dumps(
            {
                "candidate_promotion_decisions": candidate_decisions,
                "earliest_candidate_gate_pass_start": None,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="refined_earliest_candidate_gate_pass_boundary must be provided"):
        DataPlatform.from_release(release, strict=True)


def test_release_loader_validates_candidate_interval_recommendations(tmp_path):
    import json

    release = tmp_path / "india_equity_data_test"
    release.mkdir()
    candidate_decisions = [
        {
            "candidate_start": candidate_start,
            "candidate_audit_status": "FAIL",
            "decision_window_gate": "PASS",
            "warmup_gate": "PASS",
            "feature_readiness": {"feature_warmup_not_ready": False},
            "session_liquidity_gate": "PASS",
            "identity_gate": "FAIL",
            "price_action_gate": "PASS",
            "instrument_gate": "PASS",
            "status_gate": "PASS",
            "refined_earliest_passing_snapshot": "2011-01-31" if candidate_start == "2011-01-01" else None,
            "hard_failures": {
                **{key: 0 for key in EXPECTED_CANDIDATE_HARD_FAILURE_KEYS},
                "not_materialized": False,
                "candidate_start_snapshot_missing": False,
                "decision_window_snapshots_missing": False,
                "identity_failures": 1,
            },
            "promotion_interpretation": CANDIDATE_NOT_READY_INTERPRETATION,
        }
        for candidate_start in CANDIDATE_RESEARCH_START_DATES
    ]
    valid_recommendation = {
        "status": "CANDIDATE_REFINED_BOUNDARY_AVAILABLE",
        "start": "2011-01-31",
        "end": "2026-08-10",
        "profile": PROFILE_ID,
        "profile_version": PROFILE_VERSION,
        "boundary_scan_method": CANDIDATE_REFINED_BOUNDARY_SCAN_METHOD,
        "promotion_status": "NOT_PROMOTED_UNLESS_PRESENT_IN_RESEARCH_QUALITY_INTERVALS",
    }
    valid_pit_recommendation = {
        **valid_recommendation,
        "interval_type": CANDIDATE_PIT_UNIVERSE_INTERVAL_TYPE,
        "feature_readiness_policy": CANDIDATE_FEATURE_READINESS_POLICY,
    }

    def write_research_manifest(**overrides):
        (release / RESEARCH_RELEASE_MANIFEST_ARTIFACT).write_text(
            json.dumps(
                {
                    "candidate_promotion_decisions": candidate_decisions,
                    "earliest_candidate_gate_pass_start": None,
                    "refined_earliest_candidate_gate_pass_boundary": "2011-01-31",
                    "candidate_recommended_research_interval": valid_recommendation,
                    "candidate_recommended_pit_universe_interval": valid_pit_recommendation,
                    **overrides,
                }
            ),
            encoding="utf-8",
        )

    (release / DATA_RELEASE_MANIFEST_ARTIFACT).write_text(
        json.dumps(
            {
                "coverage": {"observed_start": SOURCE_OBSERVED_START_DATE, "observed_end": "2026-08-10"},
                "verified_start_date": SOURCE_OBSERVED_START_DATE,
                "verified_end_date": "2026-08-10",
                "quality_tier": "DATASET_EXPLORATORY",
            }
        ),
        encoding="utf-8",
    )
    write_research_manifest(candidate_recommended_pit_universe_interval={
        **valid_pit_recommendation,
        "feature_readiness_policy": "REQUIRED_FOR_UNIVERSE_PROMOTION",
    })
    with pytest.raises(ValueError, match="feature_readiness_policy does not separate feature readiness"):
        DataPlatform.from_release(release, strict=True)

    write_research_manifest(candidate_recommended_research_interval={
        **valid_recommendation,
        "boundary_scan_method": "COARSE_CANDIDATE_STARTS_ONLY",
    })
    with pytest.raises(ValueError, match="boundary_scan_method is not the published refined scan method"):
        DataPlatform.from_release(release, strict=True)


def test_research_manifest_contract_requires_scoped_downstream_policy(tmp_path):
    release = tmp_path / TARGET_RELEASE_ID
    release.mkdir()
    data_manifest = {
        "release_id": release.name,
        "git_commit": "abc123",
        "build_mode": SOURCE_BUILD_MODE,
        "coverage": {"observed_start": SOURCE_OBSERVED_START_DATE, "observed_end": "2026-08-10"},
        "research_coverage": {
            "research_verified_start": RESEARCH_START_DATE,
            "research_verified_end": "2026-08-10",
            "monthly_snapshot_start": CANDIDATE_MONTHLY_SNAPSHOT_START,
            "universe_profile": PROFILE_ID,
            "profile_version": PROFILE_VERSION,
            "priority_scope": PRIORITY_SCOPE,
        },
        "config_sha256": "0" * 64,
        "manual_override_sha256": "0" * 64,
    }
    valid_manifest = {
        "release_id": release.name,
        "git_sha": "abc123",
        "research_quality": {
            "status": RESEARCH_HIGH_CONFIDENCE_STATUS,
            "start": RESEARCH_START_DATE,
            "end": "2026-08-10",
            "monthly_snapshot_start": CANDIDATE_MONTHLY_SNAPSHOT_START,
            "universe_profile": PROFILE_ID,
            "profile_version": PROFILE_VERSION,
            "priority_scope": PRIORITY_SCOPE,
        },
        "source_coverage": {
            "observed_start": SOURCE_OBSERVED_START_DATE,
            "observed_end": "2026-08-10",
            "research_start": RESEARCH_START_DATE,
            "research_end": "2026-08-10",
        },
        "warmup_coverage": {
            "feature_readiness_windows": FEATURE_READINESS_WINDOWS,
            "feature_ready_dates": {"model_arena_handoff_history": "2007-03-15"},
            "required_prior_sessions_for_full_readiness": max(FEATURE_READINESS_WINDOWS.values()),
            "earliest_fully_warmed_date": "2007-03-15",
        },
        "research_quality_intervals": [
            {
                "start": RESEARCH_START_DATE,
                "end": "2026-08-10",
                "status": RESEARCH_HIGH_CONFIDENCE_STATUS,
                "profile": PROFILE_ID,
                "profile_version": PROFILE_VERSION,
                "priority_scope": PRIORITY_SCOPE,
            }
        ],
        "candidate_promotion_decisions": [
            {
                "candidate_start": candidate_start,
                "candidate_audit_status": "FAIL",
                "decision_window_gate": "PASS",
                "warmup_gate": "FAIL",
                "feature_readiness": {"feature_warmup_not_ready": True},
                "session_liquidity_gate": "PASS",
                "identity_gate": "PASS",
                "price_action_gate": "PASS",
                "instrument_gate": "PASS",

                "status_gate": "PASS",
                "refined_earliest_passing_snapshot": None,
                "hard_failures": {
                    **{key: 0 for key in EXPECTED_CANDIDATE_HARD_FAILURE_KEYS},
                    "not_materialized": False,
                    "candidate_start_snapshot_missing": False,
                    "decision_window_snapshots_missing": False,
                },
                "promotion_interpretation": CANDIDATE_NOT_READY_INTERPRETATION,
            }
            for candidate_start in CANDIDATE_RESEARCH_START_DATES
        ],
        "earliest_candidate_gate_pass_start": None,
        "refined_earliest_candidate_gate_pass_boundary": None,
        "candidate_recommended_pit_universe_interval": {
            "status": "NO_REFINED_BOUNDARY",
            "start": None,
            "end": "2026-08-10",
            "profile": PROFILE_ID,
            "profile_version": PROFILE_VERSION,
            "boundary_scan_method": CANDIDATE_REFINED_BOUNDARY_SCAN_METHOD,
            "promotion_status": "NOT_PROMOTED_UNLESS_PRESENT_IN_RESEARCH_QUALITY_INTERVALS",
            "interval_type": CANDIDATE_PIT_UNIVERSE_INTERVAL_TYPE,
            "feature_readiness_policy": CANDIDATE_FEATURE_READINESS_POLICY,
        },
        "candidate_recommended_research_interval": {
            "status": "NO_REFINED_BOUNDARY",
            "start": None,
            "end": "2026-08-10",
            "profile": PROFILE_ID,
            "profile_version": PROFILE_VERSION,
            "boundary_scan_method": CANDIDATE_REFINED_BOUNDARY_SCAN_METHOD,
            "promotion_status": "NOT_PROMOTED_UNLESS_PRESENT_IN_RESEARCH_QUALITY_INTERVALS",
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
        "candidate_required_research_securities": 14,
        "liquid_v1_securities": 8,
        "candidate_liquid_v1_securities": 11,
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
            "known_listing_date",
            "listing_date_quality",
            "observed_history_start",
            "listing_age_sessions_quality",
            "listing_history_left_censored",
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
            "feature_ready_60",
            "feature_ready_126",
            "signal_history_ready_252",
            "signal_history_ready_273",
            "model_handoff_history_ready_300",
            "feature_readiness_source",
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
        "candidate_promotion_audit_sha256": "0" * 64,
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

    stale_config_hash = {**valid_manifest, "config_sha256": "1" * 64}
    failures = research_manifest_contract_failures(release, data_manifest, stale_config_hash)
    assert "research manifest config_sha256 does not match data manifest" in failures

    missing_ci_status_hash = {key: value for key, value in valid_manifest.items() if key != "ci_status_sha256"}
    failures = research_manifest_contract_failures(release, data_manifest, missing_ci_status_hash)
    assert "research manifest ci_status_sha256 is missing or invalid" in failures

    missing_candidate_decisions = {key: value for key, value in valid_manifest.items() if key != "candidate_promotion_decisions"}
    failures = research_manifest_contract_failures(release, data_manifest, missing_candidate_decisions)
    assert "research manifest candidate_promotion_decisions is missing or not a list" in failures

    pre_warmup_rhc = {
        **valid_manifest,
        "research_quality_intervals": [
            {
                "start": "2007-01-31",
                "end": "2026-08-10",
                "status": RESEARCH_HIGH_CONFIDENCE_STATUS,
                "profile": PROFILE_ID,
                "profile_version": PROFILE_VERSION,
                "priority_scope": PRIORITY_SCOPE,
            }
        ],
    }
    failures = research_manifest_contract_failures(release, data_manifest, pre_warmup_rhc)
    assert "research manifest pre-2013 RESEARCH_HIGH_CONFIDENCE interval starts before earliest fully warmed date" in failures

    stale_candidate_decisions = {
        **valid_manifest,
        "candidate_promotion_decisions": valid_manifest["candidate_promotion_decisions"][:-1],
    }
    failures = research_manifest_contract_failures(release, data_manifest, stale_candidate_decisions)
    assert any("candidate_promotion_decisions misses" in failure for failure in failures)

    duplicate_candidate_decisions = {
        **valid_manifest,
        "candidate_promotion_decisions": [
            *valid_manifest["candidate_promotion_decisions"],
            valid_manifest["candidate_promotion_decisions"][0],
        ],
    }
    failures = research_manifest_contract_failures(release, data_manifest, duplicate_candidate_decisions)
    assert any("candidate_promotion_decisions has duplicate starts" in failure for failure in failures)

    malformed_candidate_decision = {
        **valid_manifest,
        "candidate_promotion_decisions": [
            {
                key: value for key, value in valid_manifest["candidate_promotion_decisions"][0].items()
                if key != "hard_failures"
            },
            *valid_manifest["candidate_promotion_decisions"][1:],
        ],
    }
    failures = research_manifest_contract_failures(release, data_manifest, malformed_candidate_decision)
    assert any("decision misses" in failure and "hard_failures" in failure for failure in failures)

    missing_decision_window_gate = {
        **valid_manifest,
        "candidate_promotion_decisions": [
            {
                key: value for key, value in valid_manifest["candidate_promotion_decisions"][0].items()
                if key != "decision_window_gate"
            },
            *valid_manifest["candidate_promotion_decisions"][1:],
        ],
    }
    failures = research_manifest_contract_failures(release, data_manifest, missing_decision_window_gate)
    assert any("decision misses" in failure and "decision_window_gate" in failure for failure in failures)

    invalid_decision_window_gate = {
        **valid_manifest,
        "candidate_promotion_decisions": [
            {
                **valid_manifest["candidate_promotion_decisions"][0],
                "decision_window_gate": "UNKNOWN",
            },
            *valid_manifest["candidate_promotion_decisions"][1:],
        ],
    }
    failures = research_manifest_contract_failures(release, data_manifest, invalid_decision_window_gate)
    assert any("invalid decision_window_gate" in failure for failure in failures)

    missing_status_gate = {
        **valid_manifest,
        "candidate_promotion_decisions": [
            {
                key: value for key, value in valid_manifest["candidate_promotion_decisions"][0].items()
                if key != "status_gate"
            },
            *valid_manifest["candidate_promotion_decisions"][1:],
        ],
    }
    failures = research_manifest_contract_failures(release, data_manifest, missing_status_gate)
    assert any("decision misses" in failure and "status_gate" in failure for failure in failures)

    invalid_status_gate = {
        **valid_manifest,
        "candidate_promotion_decisions": [
            {
                **valid_manifest["candidate_promotion_decisions"][0],
                "status_gate": "UNKNOWN",
            },
            *valid_manifest["candidate_promotion_decisions"][1:],
        ],
    }
    failures = research_manifest_contract_failures(release, data_manifest, invalid_status_gate)
    assert any("invalid status_gate" in failure for failure in failures)

    incomplete_candidate_hard_failures = {
        **valid_manifest,
        "candidate_promotion_decisions": [
            {
                **valid_manifest["candidate_promotion_decisions"][0],
                "hard_failures": {"identity_failures": 1},
            },
            *valid_manifest["candidate_promotion_decisions"][1:],
        ],
    }
    failures = research_manifest_contract_failures(release, data_manifest, incomplete_candidate_hard_failures)
    assert any("hard_failures keys do not match" in failure for failure in failures)

    mistyped_candidate_hard_failures = {
        **valid_manifest,
        "candidate_promotion_decisions": [
            {
                **valid_manifest["candidate_promotion_decisions"][0],
                "hard_failures": {
                    **valid_manifest["candidate_promotion_decisions"][0]["hard_failures"],
                },
            },
            *valid_manifest["candidate_promotion_decisions"][1:],
        ],
    }
    failures = research_manifest_contract_failures(release, data_manifest, mistyped_candidate_hard_failures)
    assert any("hard_failures value types do not match" in failure for failure in failures)

    pass_candidate_audit_with_active_hard_failure = {
        **valid_manifest,
        "candidate_promotion_decisions": [
            {
                **valid_manifest["candidate_promotion_decisions"][0],
                "candidate_audit_status": "PASS",
                "hard_failures": {
                    **valid_manifest["candidate_promotion_decisions"][0]["hard_failures"],
                    "candidate_start_snapshot_missing": True,
                },
            },
            *valid_manifest["candidate_promotion_decisions"][1:],
        ],
    }
    failures = research_manifest_contract_failures(release, data_manifest, pass_candidate_audit_with_active_hard_failure)
    assert any("claims PASS candidate audit with active hard_failures" in failure for failure in failures)

    fail_candidate_audit_without_active_hard_failure = {
        **valid_manifest,
        "candidate_promotion_decisions": [
            {
                **valid_manifest["candidate_promotion_decisions"][0],
                "candidate_audit_status": "FAIL",
                "warmup_gate": "PASS",
                "feature_readiness": {"feature_warmup_not_ready": True},
                "hard_failures": {
                    **valid_manifest["candidate_promotion_decisions"][0]["hard_failures"],
                },
            },
            *valid_manifest["candidate_promotion_decisions"][1:],
        ],
    }
    failures = research_manifest_contract_failures(release, data_manifest, fail_candidate_audit_without_active_hard_failure)
    assert any("claims FAIL candidate audit without active hard_failures" in failure for failure in failures)

    contradictory_decision_window_gate = {
        **valid_manifest,
        "candidate_promotion_decisions": [
            {
                **valid_manifest["candidate_promotion_decisions"][0],
                "decision_window_gate": "PASS",
                "hard_failures": {
                    **valid_manifest["candidate_promotion_decisions"][0]["hard_failures"],
                    "decision_window_snapshots_missing": True,
                },
            },
            *valid_manifest["candidate_promotion_decisions"][1:],
        ],
    }
    failures = research_manifest_contract_failures(release, data_manifest, contradictory_decision_window_gate)
    assert any("decision_window_gate contradicts hard_failures" in failure for failure in failures)

    contradictory_warmup_gate = {
        **valid_manifest,
        "candidate_promotion_decisions": [
            {
                **valid_manifest["candidate_promotion_decisions"][0],
                "warmup_gate": "PASS",
                "feature_readiness": {"feature_warmup_not_ready": True},
                "hard_failures": {
                    **valid_manifest["candidate_promotion_decisions"][0]["hard_failures"],
                },
            },
            *valid_manifest["candidate_promotion_decisions"][1:],
        ],
    }
    failures = research_manifest_contract_failures(release, data_manifest, contradictory_warmup_gate)
    assert any("warmup_gate contradicts feature_readiness" in failure for failure in failures)

    contradictory_session_liquidity_gate = {
        **valid_manifest,
        "candidate_promotion_decisions": [
            {
                **valid_manifest["candidate_promotion_decisions"][0],
                "session_liquidity_gate": "PASS",
                "hard_failures": {
                    **valid_manifest["candidate_promotion_decisions"][0]["hard_failures"],
                    "session_liquidity_window_failures": 1,
                },
            },
            *valid_manifest["candidate_promotion_decisions"][1:],
        ],
    }
    failures = research_manifest_contract_failures(release, data_manifest, contradictory_session_liquidity_gate)
    assert any("session_liquidity_gate contradicts hard_failures" in failure for failure in failures)

    contradictory_identity_gate = {
        **valid_manifest,
        "candidate_promotion_decisions": [
            {
                **valid_manifest["candidate_promotion_decisions"][0],
                "identity_gate": "PASS",
                "hard_failures": {
                    **valid_manifest["candidate_promotion_decisions"][0]["hard_failures"],
                    "identity_failures": 1,
                },
            },
            *valid_manifest["candidate_promotion_decisions"][1:],
        ],
    }
    failures = research_manifest_contract_failures(release, data_manifest, contradictory_identity_gate)
    assert any("identity_gate contradicts hard_failures" in failure for failure in failures)

    contradictory_price_action_gate = {
        **valid_manifest,
        "candidate_promotion_decisions": [
            {
                **valid_manifest["candidate_promotion_decisions"][0],
                "price_action_gate": "PASS",
                "hard_failures": {
                    **valid_manifest["candidate_promotion_decisions"][0]["hard_failures"],
                    "signal_window_non_pass_boundaries": 1,
                },
            },
            *valid_manifest["candidate_promotion_decisions"][1:],
        ],
    }
    failures = research_manifest_contract_failures(release, data_manifest, contradictory_price_action_gate)
    assert any("price_action_gate contradicts hard_failures" in failure for failure in failures)

    contradictory_instrument_gate = {
        **valid_manifest,
        "candidate_promotion_decisions": [
            {
                **valid_manifest["candidate_promotion_decisions"][0],
                "instrument_gate": "PASS",

                "status_gate": "PASS",
                "hard_failures": {
                    **valid_manifest["candidate_promotion_decisions"][0]["hard_failures"],
                    "instrument_failures": 1,
                },
            },
            *valid_manifest["candidate_promotion_decisions"][1:],
        ],
    }
    failures = research_manifest_contract_failures(release, data_manifest, contradictory_instrument_gate)
    assert any("instrument_gate contradicts hard_failures" in failure for failure in failures)

    contradictory_status_gate = {
        **valid_manifest,
        "candidate_promotion_decisions": [
            {
                **valid_manifest["candidate_promotion_decisions"][0],
                "status_gate": "PASS",
                "hard_failures": {
                    **valid_manifest["candidate_promotion_decisions"][0]["hard_failures"],
                    "status_failures": 1,
                },
            },
            *valid_manifest["candidate_promotion_decisions"][1:],
        ],
    }
    failures = research_manifest_contract_failures(release, data_manifest, contradictory_status_gate)
    assert any("status_gate contradicts hard_failures" in failure for failure in failures)

    invalid_candidate_interpretation = {
        **valid_manifest,
        "candidate_promotion_decisions": [
            {
                **valid_manifest["candidate_promotion_decisions"][0],
                "promotion_interpretation": "PASS",
            },
            *valid_manifest["candidate_promotion_decisions"][1:],
        ],
    }
    failures = research_manifest_contract_failures(release, data_manifest, invalid_candidate_interpretation)
    assert any("invalid promotion_interpretation" in failure for failure in failures)

    contradictory_candidate_pass = {
        **valid_manifest,
        "candidate_promotion_decisions": [
            {
                **valid_manifest["candidate_promotion_decisions"][0],
                "candidate_audit_status": "PASS",
                "decision_window_gate": "PASS",
                "promotion_interpretation": CANDIDATE_GATE_PASS_INTERPRETATION,
            },
            *valid_manifest["candidate_promotion_decisions"][1:],
        ],
    }
    failures = research_manifest_contract_failures(release, data_manifest, contradictory_candidate_pass)
    assert any("claims gate pass with non-PASS gates" in failure for failure in failures)

    invalid_earliest_candidate = {**valid_manifest, "earliest_candidate_gate_pass_start": "2010-01-01"}
    failures = research_manifest_contract_failures(release, data_manifest, invalid_earliest_candidate)
    assert "research manifest earliest_candidate_gate_pass_start is not a configured candidate start" in failures

    unmatched_earliest_candidate = {**valid_manifest, "earliest_candidate_gate_pass_start": CANDIDATE_RESEARCH_START_DATES[0]}
    failures = research_manifest_contract_failures(release, data_manifest, unmatched_earliest_candidate)
    assert "research manifest earliest_candidate_gate_pass_start does not match exactly one gate-pass candidate decision" in failures

    gate_pass_decision = {
        "candidate_audit_status": "PASS",
        "decision_window_gate": "PASS",
        "warmup_gate": "PASS",
        "feature_readiness": {"feature_warmup_not_ready": False},
        "session_liquidity_gate": "PASS",
        "identity_gate": "PASS",
        "price_action_gate": "PASS",
        "instrument_gate": "PASS",

        "status_gate": "PASS",
        "hard_failures": {
            **{key: 0 for key in EXPECTED_CANDIDATE_HARD_FAILURE_KEYS},
            "not_materialized": False,
            "candidate_start_snapshot_missing": False,
            "decision_window_snapshots_missing": False,
        },
        "promotion_interpretation": CANDIDATE_GATE_PASS_INTERPRETATION,
    }
    non_earliest_gate_pass = {
        **valid_manifest,
        "candidate_promotion_decisions": [
            {**valid_manifest["candidate_promotion_decisions"][0], **gate_pass_decision},
            {**valid_manifest["candidate_promotion_decisions"][1], **gate_pass_decision},
            *valid_manifest["candidate_promotion_decisions"][2:],
        ],
        "earliest_candidate_gate_pass_start": valid_manifest["candidate_promotion_decisions"][1]["candidate_start"],
    }
    failures = research_manifest_contract_failures(release, data_manifest, non_earliest_gate_pass)
    assert "research manifest earliest_candidate_gate_pass_start is not the earliest gate-pass candidate" in failures

    missing_gate_pass_start = {
        **valid_manifest,
        "candidate_promotion_decisions": [
            {**valid_manifest["candidate_promotion_decisions"][0], **gate_pass_decision},
            *valid_manifest["candidate_promotion_decisions"][1:],
        ],
        "earliest_candidate_gate_pass_start": None,
    }
    failures = research_manifest_contract_failures(release, data_manifest, missing_gate_pass_start)
    assert "research manifest earliest_candidate_gate_pass_start is null despite gate-pass candidate decisions" in failures

    missing_earliest_candidate = {key: value for key, value in valid_manifest.items() if key != "earliest_candidate_gate_pass_start"}
    failures = research_manifest_contract_failures(release, data_manifest, missing_earliest_candidate)
    assert "research manifest earliest_candidate_gate_pass_start is missing" in failures

    missing_refined_candidate_boundary = {
        key: value for key, value in valid_manifest.items()
        if key != "refined_earliest_candidate_gate_pass_boundary"
    }
    failures = research_manifest_contract_failures(release, data_manifest, missing_refined_candidate_boundary)
    assert "research manifest refined_earliest_candidate_gate_pass_boundary is missing despite refined candidate row evidence" in failures

    missing_recommended_interval = {
        key: value for key, value in valid_manifest.items()
        if key != "candidate_recommended_research_interval"
    }
    failures = research_manifest_contract_failures(release, data_manifest, missing_recommended_interval)
    assert "research manifest candidate_recommended_research_interval is missing or not an object" in failures

    missing_pit_universe_interval = {
        key: value for key, value in valid_manifest.items()
        if key != "candidate_recommended_pit_universe_interval"
    }
    failures = research_manifest_contract_failures(release, data_manifest, missing_pit_universe_interval)
    assert "research manifest candidate_recommended_pit_universe_interval is missing or not an object" in failures

    promoted_recommended_interval = {
        **valid_manifest,
        "candidate_recommended_research_interval": {
            **valid_manifest["candidate_recommended_research_interval"],
            "promotion_status": "PROMOTED",
        },
    }
    failures = research_manifest_contract_failures(release, data_manifest, promoted_recommended_interval)
    assert "research manifest candidate_recommended_research_interval.promotion_status is not fail-closed" in failures

    stale_scan_method_interval = {
        **valid_manifest,
        "candidate_recommended_research_interval": {
            **valid_manifest["candidate_recommended_research_interval"],
            "boundary_scan_method": "COARSE_CANDIDATE_STARTS_ONLY",
        },
    }
    failures = research_manifest_contract_failures(release, data_manifest, stale_scan_method_interval)
    assert "research manifest candidate_recommended_research_interval.boundary_scan_method is not the published refined scan method" in failures

    feature_conflated_pit_interval = {
        **valid_manifest,
        "candidate_recommended_pit_universe_interval": {
            **valid_manifest["candidate_recommended_pit_universe_interval"],
            "feature_readiness_policy": "REQUIRED_FOR_UNIVERSE_PROMOTION",
        },
    }
    failures = research_manifest_contract_failures(release, data_manifest, feature_conflated_pit_interval)
    assert "research manifest candidate_recommended_pit_universe_interval.feature_readiness_policy does not separate feature readiness" in failures

    mismatched_recommended_interval = {
        **valid_manifest,
        "candidate_recommended_research_interval": {
            **valid_manifest["candidate_recommended_research_interval"],
            "start": "2007-01-31",
        },
    }
    failures = research_manifest_contract_failures(release, data_manifest, mismatched_recommended_interval)
    assert "research manifest candidate_recommended_research_interval.start does not match refined boundary" in failures

    missing_partition_hash = {key: value for key, value in valid_manifest.items() if key != "partitioned_artifacts_manifest_sha256"}
    failures = research_manifest_contract_failures(release, data_manifest, missing_partition_hash)
    assert "research manifest partitioned_artifacts_manifest_sha256 is missing or invalid" in failures

    missing_candidate_audit_hash = {key: value for key, value in valid_manifest.items() if key != "candidate_promotion_audit_sha256"}
    failures = research_manifest_contract_failures(release, data_manifest, missing_candidate_audit_hash)
    assert "research manifest candidate_promotion_audit_sha256 is missing or invalid" in failures

    missing_candidate_count = {key: value for key, value in valid_manifest.items() if key != "candidate_required_research_securities"}
    failures = research_manifest_contract_failures(release, data_manifest, missing_candidate_count)
    assert "research manifest candidate_required_research_securities is missing or not an integer" in failures

    inconsistent_candidate_count = {**valid_manifest, "candidate_required_research_securities": 9}
    failures = research_manifest_contract_failures(release, data_manifest, inconsistent_candidate_count)
    assert "research manifest candidate_required_research_securities is smaller than required_research_securities" in failures

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
            "observed_start": SOURCE_OBSERVED_START_DATE,
            "observed_end": "2026-08-10",
            "security_count": 2,
            "observation_count": 3,
        },
        "source_coverage": {
            "source_verified_start": SOURCE_OBSERVED_START_DATE,
            "source_verified_end": "2026-08-10",
            "verification_basis": "official NSE market-data files; no independent exchange calendar claim",
        },
        "research_coverage": {
            "research_verified_start": RESEARCH_START_DATE,
            "research_verified_end": "2026-08-10",
            "monthly_snapshot_start": CANDIDATE_MONTHLY_SNAPSHOT_START,
            "universe_profile": PROFILE_ID,
            "profile_version": PROFILE_VERSION,
            "priority_scope": PRIORITY_SCOPE,
        },
        "warmup_coverage": {
            "feature_readiness_windows": FEATURE_READINESS_WINDOWS,
            "feature_ready_dates": {"model_arena_handoff_history": "2007-03-15"},
            "required_prior_sessions_for_full_readiness": max(FEATURE_READINESS_WINDOWS.values()),
            "earliest_fully_warmed_date": "2007-03-15",
        },
        "research_quality_intervals": [
            {
                "start": RESEARCH_START_DATE,
                "end": "2026-08-10",
                "status": RESEARCH_HIGH_CONFIDENCE_STATUS,
                "profile": PROFILE_ID,
                "profile_version": PROFILE_VERSION,
                "priority_scope": PRIORITY_SCOPE,
            }
        ],
        "component_quality": COMPONENT_QUALITY,
        "source_manifest_sha256": "0" * 64,
        "config_sha256": "0" * 64,
        "manual_override_sha256": "0" * 64,
        "definition": ACTIVE_DEFINITION,
        "quality_tier": DATASET_QUALITY_TIER,
        "parser_versions": PARSER_VERSIONS,
        "artifacts": {
            **{f"release/{name}": "0" * 64 for name in REQUIRED if name not in {DATA_RELEASE_MANIFEST_ARTIFACT, RESEARCH_RELEASE_MANIFEST_ARTIFACT}},
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

    pre_warmup_rhc = {
        **manifest,
        "research_quality_intervals": [
            {
                "start": "2007-01-31",
                "end": "2026-08-10",
                "status": RESEARCH_HIGH_CONFIDENCE_STATUS,
                "profile": PROFILE_ID,
                "profile_version": PROFILE_VERSION,
                "priority_scope": PRIORITY_SCOPE,
            }
        ],
    }
    failures = data_manifest_contract_failures(release, pre_warmup_rhc)
    assert "data manifest pre-2013 RESEARCH_HIGH_CONFIDENCE interval starts before earliest fully warmed date" in failures

    missing_monthly_snapshot_start = {
        **manifest,
        "research_coverage": {
            key: value for key, value in manifest["research_coverage"].items()
            if key != "monthly_snapshot_start"
        },
    }
    failures = data_manifest_contract_failures(release, missing_monthly_snapshot_start)
    assert "data manifest research_coverage.monthly_snapshot_start is missing" in failures

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
    assert summary["failure_count"] == 1 + len(EXPECTED_INVARIANT_VALIDATION_METRICS - {"duplicate_month_security_rows", "required_artifact_identity_quality_failures"})
    assert summary["failures"] == {"required_artifact_identity_quality_failures": 2}
    assert "monthly_snapshot_start_mismatch" in summary["missing_metrics"]


def test_candidate_promotion_audit_summary_requires_warmup_evidence():
    valid_row = {
        "candidate_start": "2011-01-01",
        "profile": PROFILE_ID,
        "profile_version": PROFILE_VERSION,
        "priority_scope": PRIORITY_SCOPE,
        "control_start": RESEARCH_START_DATE,
        "required_prior_sessions_for_full_readiness": max(FEATURE_READINESS_WINDOWS.values()),
        "status": "PASS",
        "required_rows": 10,
        "fully_warmed_required_rows": 10,
        "monthly_snapshots_after_decision": 1,
        "feature_readiness": {"feature_warmup_not_ready": False},
        "feature_model_readiness_complete": True,
        "pit_universe_gate_pass": True,
        "refined_earliest_passing_snapshot": "2011-01-31",
        "hard_failures": {key: 0 for key in EXPECTED_CANDIDATE_HARD_FAILURE_KEYS},
    }
    valid_row["hard_failures"]["not_materialized"] = False
    valid_row["hard_failures"]["candidate_start_snapshot_missing"] = False
    valid_row["hard_failures"]["decision_window_snapshots_missing"] = False

    stale_row = {
        **valid_row,
        "candidate_start": "2009-01-01",
        "fully_warmed_required_rows": 9,
        "feature_readiness": {"feature_warmup_not_ready": True},
        "feature_model_readiness_complete": False,
    }
    missing_evidence_row = {key: value for key, value in {**valid_row, "candidate_start": "2007-01-01"}.items() if key != "required_rows"}
    valid_2006_row = {**valid_row, "candidate_start": "2006-01-01"}

    valid_report = {
        "profile": PROFILE_ID,
        "profile_version": PROFILE_VERSION,
        "priority_scope": PRIORITY_SCOPE,
        "control_start": RESEARCH_START_DATE,
        "candidate_start_dates": list(CANDIDATE_RESEARCH_START_DATES),
        "refined_boundary_scan_method": CANDIDATE_REFINED_BOUNDARY_SCAN_METHOD,
        "required_prior_sessions_for_full_readiness": max(FEATURE_READINESS_WINDOWS.values()),
        "candidate_audits": [valid_row, stale_row, missing_evidence_row, valid_2006_row],
    }

    summary = candidate_promotion_audit_summary(valid_report)

    assert summary["missing_candidate_starts"] == []
    assert summary["unexpected_candidate_starts"] == []
    assert summary["duplicate_candidate_starts"] == []
    assert summary["malformed_candidate_audits"] == ["2007-01-01"]
    assert summary["malformed_candidate_report"] == []

    duplicate_summary = candidate_promotion_audit_summary({**valid_report, "candidate_audits": [valid_row, {**valid_row}]})
    assert duplicate_summary["duplicate_candidate_starts"] == ["2011-01-01"]

    stale_scan_method_summary = candidate_promotion_audit_summary({
        **valid_report,
        "refined_boundary_scan_method": "COARSE_CANDIDATE_STARTS_ONLY",
    })
    assert stale_scan_method_summary["malformed_candidate_report"] == ["refined_boundary_scan_method"]

    unexpected_summary = candidate_promotion_audit_summary({**valid_report, "candidate_audits": [valid_row, {**valid_row, "candidate_start": "2010-01-01"}]})
    assert unexpected_summary["unexpected_candidate_starts"] == ["2010-01-01"]

    wrong_control_summary = candidate_promotion_audit_summary({**valid_report, "candidate_audits": [valid_row, {**valid_row, "candidate_start": "2009-01-01", "control_start": "2012-01-01"}, {**valid_row, "candidate_start": "2007-01-01"}, {**valid_row, "candidate_start": "2006-01-01"}]})
    assert wrong_control_summary["malformed_candidate_audits"] == ["2009-01-01"]

    contradictory_decision_window = {
        **valid_row,
        "candidate_start": "2009-01-01",
        "status": "FAIL",
        "monthly_snapshots_after_decision": 0,
        "hard_failures": {
            **valid_row["hard_failures"],
            "decision_window_snapshots_missing": False,
        },
    }
    contradictory_summary = candidate_promotion_audit_summary({
        **valid_report,
        "candidate_audits": [
            valid_row,
            contradictory_decision_window,
            {**valid_row, "candidate_start": "2007-01-01"},
            {**valid_row, "candidate_start": "2006-01-01"},
        ],
    })
    assert contradictory_summary["malformed_candidate_audits"] == ["2009-01-01"]

    pass_with_active_failure = {
        **valid_row,
        "candidate_start": "2009-01-01",
        "status": "PASS",
        "hard_failures": {
            **valid_row["hard_failures"],
            "identity_failures": 1,
        },
    }
    active_failure_summary = candidate_promotion_audit_summary({
        **valid_report,
        "candidate_audits": [
            valid_row,
            pass_with_active_failure,
            {**valid_row, "candidate_start": "2007-01-01"},
            {**valid_row, "candidate_start": "2006-01-01"},
        ],
    })
    assert active_failure_summary["malformed_candidate_audits"] == ["2009-01-01"]

    fail_without_active_failure = {
        **valid_row,
        "candidate_start": "2009-01-01",
        "status": "FAIL",
    }
    inactive_failure_summary = candidate_promotion_audit_summary({
        **valid_report,
        "candidate_audits": [
            valid_row,
            fail_without_active_failure,
            {**valid_row, "candidate_start": "2007-01-01"},
            {**valid_row, "candidate_start": "2006-01-01"},
        ],
    })
    assert inactive_failure_summary["malformed_candidate_audits"] == ["2009-01-01"]

    mistyped_hard_failure_row = {
        **valid_row,
        "candidate_start": "2009-01-01",
        "hard_failures": {
            **valid_row["hard_failures"],
            "identity_failures": False,
        },
    }
    mistyped_summary = candidate_promotion_audit_summary({
        **valid_report,
        "candidate_audits": [
            valid_row,
            mistyped_hard_failure_row,
            {**valid_row, "candidate_start": "2007-01-01"},
            {**valid_row, "candidate_start": "2006-01-01"},
        ],
    })
    assert mistyped_summary["malformed_candidate_audits"] == ["2009-01-01"]

    missing_refined_snapshot_row = {
        key: value for key, value in {**valid_row, "candidate_start": "2009-01-01"}.items()
        if key != "refined_earliest_passing_snapshot"
    }
    missing_refined_summary = candidate_promotion_audit_summary({
        **valid_report,
        "candidate_audits": [
            valid_row,
            missing_refined_snapshot_row,
            {**valid_row, "candidate_start": "2007-01-01"},
            {**valid_row, "candidate_start": "2006-01-01"},
        ],
    })
    assert missing_refined_summary["malformed_candidate_audits"] == ["2009-01-01"]

    mistyped_refined_snapshot_row = {
        **valid_row,
        "candidate_start": "2009-01-01",
        "refined_earliest_passing_snapshot": 20110131,
    }
    mistyped_refined_summary = candidate_promotion_audit_summary({
        **valid_report,
        "candidate_audits": [
            valid_row,
            mistyped_refined_snapshot_row,
            {**valid_row, "candidate_start": "2007-01-01"},
            {**valid_row, "candidate_start": "2006-01-01"},
        ],
    })
    assert mistyped_refined_summary["malformed_candidate_audits"] == ["2009-01-01"]

    stale_report_summary = candidate_promotion_audit_summary({**valid_report, "candidate_start_dates": ["2011-01-01"]})
    assert stale_report_summary["malformed_candidate_report"] == ["candidate_start_dates"]


def test_candidate_manifest_decisions_match_candidate_audit_report():
    hard_failures = {key: 0 for key in EXPECTED_CANDIDATE_HARD_FAILURE_KEYS}
    hard_failures["not_materialized"] = False
    hard_failures["candidate_start_snapshot_missing"] = False
    hard_failures["decision_window_snapshots_missing"] = False
    manifest = {
        "candidate_promotion_decisions": [
            {
                "candidate_start": "2011-01-01",
                "candidate_audit_status": "PASS",
                "feature_readiness": {"feature_warmup_not_ready": False},
                "feature_model_readiness_complete": True,
                "pit_universe_gate_pass": True,
                "refined_earliest_passing_snapshot": "2011-01-31",
                "hard_failures": hard_failures,
            }
        ]
    }
    report = {
        "candidate_audits": [
            {
                "candidate_start": "2011-01-01",
                "status": "PASS",
                "feature_readiness": {"feature_warmup_not_ready": False},
                "feature_model_readiness_complete": True,
                "pit_universe_gate_pass": True,
                "refined_earliest_passing_snapshot": "2011-01-31",
                "hard_failures": hard_failures,
            }
        ]
    }

    assert candidate_manifest_audit_consistency_failures(manifest, report) == []

    stale_manifest = {
        "candidate_promotion_decisions": [
            {
                **manifest["candidate_promotion_decisions"][0],
                "candidate_audit_status": "FAIL",
            }
        ]
    }
    assert candidate_manifest_audit_consistency_failures(stale_manifest, report) == [
        "candidate 2011-01-01 decision status does not match candidate audit report"
    ]

    stale_hard_failures = {
        "candidate_promotion_decisions": [
            {
                **manifest["candidate_promotion_decisions"][0],
                "hard_failures": {**hard_failures, "identity_failures": 1},
            }
        ]
    }
    assert candidate_manifest_audit_consistency_failures(stale_hard_failures, report) == [
        "candidate 2011-01-01 decision hard_failures do not match candidate audit report"
    ]

    stale_feature_readiness = {
        "candidate_promotion_decisions": [
            {
                **manifest["candidate_promotion_decisions"][0],
                "feature_readiness": {"feature_warmup_not_ready": True},
            }
        ]
    }
    assert candidate_manifest_audit_consistency_failures(stale_feature_readiness, report) == [
        "candidate 2011-01-01 decision feature_readiness does not match candidate audit report"
    ]

    stale_feature_model_readiness = {
        "candidate_promotion_decisions": [
            {
                **manifest["candidate_promotion_decisions"][0],
                "feature_model_readiness_complete": False,
            }
        ]
    }
    assert candidate_manifest_audit_consistency_failures(stale_feature_model_readiness, report) == [
        "candidate 2011-01-01 decision feature_model_readiness_complete does not match candidate audit report"
    ]

    stale_pit_universe_gate = {
        "candidate_promotion_decisions": [
            {
                **manifest["candidate_promotion_decisions"][0],
                "pit_universe_gate_pass": False,
            }
        ]
    }
    assert candidate_manifest_audit_consistency_failures(stale_pit_universe_gate, report) == [
        "candidate 2011-01-01 decision pit_universe_gate_pass does not match candidate audit report"
    ]

    stale_refined_snapshot = {
        "candidate_promotion_decisions": [
            {
                **manifest["candidate_promotion_decisions"][0],
                "refined_earliest_passing_snapshot": "2011-02-28",
            }
        ]
    }
    assert candidate_manifest_audit_consistency_failures(stale_refined_snapshot, report) == [
        "candidate 2011-01-01 decision refined_earliest_passing_snapshot does not match candidate audit report"
    ]


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

    path = tmp_path / ACTIVE_UNIVERSE_ARTIFACT
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

    path = tmp_path / RESEARCH_UNIVERSE_MONTHLY_ARTIFACT
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

    path = tmp_path / RESEARCH_UNIVERSE_MONTHLY_ARTIFACT
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
