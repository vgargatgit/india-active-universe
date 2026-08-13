"""Published universe profile contracts."""

TARGET_RELEASE_ID = "india_equity_data_v2.2.9"
SOURCE_BUILD_MODE = "SOURCE_BUILD"
CACHED_PROMOTION_BUILD_MODE = "CACHED_PROMOTION"
PROFILE_ID = "NSE_BROAD_LIQUID_PIT_V1"
PROFILE_VERSION = "LIQUID_V1"
PRIORITY_SCOPE = "LIQUID_V1_OR_HISTORICAL_TOP750"
SOURCE_OBSERVED_START_DATE = "2004-01-01"
PRE2006_RECON_TARGET_START_DATE = "2004-01-01"
RESEARCH_START_DATE = "2013-01-01"
RESEARCH_MONTHLY_SNAPSHOT_START = "2013-01-31"
CANDIDATE_MONTHLY_SNAPSHOT_START = "2006-01-31"
CURRENT_PROVEN_RESEARCH_START_DATE = "2013-01-01"
CURRENT_PROVEN_RESEARCH_END_DATE = "2026-08-10"
REQUIRED_QUALITY_THRESHOLD = "RESEARCH_IDENTITY_OK_AND_PRICE_ACTION_OK_FOR_LIQUID_V1_OR_HISTORICAL_TOP750"
SIGNAL_POLICY = "price-return adjusted close"
EXECUTION_POLICY = "raw nominal OHLC"
TERMINAL_VALUE_POLICY = "explicit recovery scenarios; no invented canonical value"
RECOMMENDED_SIGNAL_PRICE_SERIES = "price_return_adjusted_close"
RAW_EXECUTION_PRICE_ARTIFACT = "daily_prices_raw.parquet"
ADJUSTED_PRICE_ARTIFACT = "daily_prices_adjusted.parquet"
LIQUIDITY_ARTIFACT = "liquidity_features.parquet"
ACTIVE_UNIVERSE_ARTIFACT = "active_universe_daily.parquet"
SECURITY_MASTER_ARTIFACT = "security_master.parquet"
CORPORATE_ACTIONS_ARTIFACT = "corporate_actions.parquet"
CORPORATE_ACTION_BOUNDARY_ARTIFACT = "corporate_action_boundary_validation.parquet"
TRADING_CALENDAR_ARTIFACT = "trading_calendar.parquet"
TRADING_STATUS_INTERVALS_ARTIFACT = "trading_status_intervals.parquet"
SUSPENSION_EVENTS_ARTIFACT = "suspension_events_resolved.parquet"
TERMINAL_EVENTS_ARTIFACT = "terminal_events.parquet"
RESEARCH_UNIVERSE_MONTHLY_ARTIFACT = "research_universe_monthly.parquet"
REQUIRED_RESEARCH_SECURITY_ARTIFACT = "required_research_security.parquet"
DATA_RELEASE_MANIFEST_ARTIFACT = "data_release_manifest.json"
RESEARCH_RELEASE_MANIFEST_ARTIFACT = "research_release_manifest.json"
PARTITIONED_ARTIFACTS_MANIFEST = "partitioned_artifacts_manifest.json"
SOURCE_MANIFEST_ARTIFACT = "source_manifest.json"
SUSPENSION_SOURCE_MANIFEST_ARTIFACT = "suspension_source_manifest.json"
CORPORATE_ACTION_EVIDENCE_ARTIFACT = "corporate_action_evidence.yaml"
TERMINAL_VALUE_POLICY_REQUIREMENT = "DOWNSTREAM_RECOVERY_SENSITIVITY_REQUIRED_WHEN_CANONICAL_TERMINAL_VALUE_UNKNOWN"
DATASET_QUALITY_TIER = "DATASET_EXPLORATORY"
ACTIVE_DEFINITION = "ACTIVE_V1"
PARSER_VERSIONS = {
    "nse_bhavcopy": "nse-bhavcopy-v3",
    "canonicalization": "identity-v2",
}
RESEARCH_HIGH_CONFIDENCE_STATUS = "RESEARCH_HIGH_CONFIDENCE"
RESEARCH_EXPLORATORY_STATUS = "RESEARCH_EXPLORATORY"
SOURCE_ONLY_STATUS = "SOURCE_ONLY"
FEATURE_WARMUP_STATUS = "FEATURE_WARMUP"
COMPONENT_QUALITY = {
    "raw_source": "SOURCE_HIGH_CONFIDENCE",
    "raw_ohlcv": RESEARCH_HIGH_CONFIDENCE_STATUS,
    "research_universe_2013_onward": RESEARCH_HIGH_CONFIDENCE_STATUS,
    "terminal_events": "PARTIAL",
    "total_return": "PARTIAL",
}

LIQUID_V1_DEFINITION = {
    "instrument_type": "ORDINARY_EQUITY",
    "active": True,
    "trading_status": "ACTIVE_TRADING",
    "price_min": 20,
    "listing_age_sessions_min": 272,
    "positive_volume_days_60_min": 40,
    "median_traded_value_60_min": 5_000_000,
}

TOP_LIQUIDITY_RANKING_METRIC = "median_traded_value_126"
FEATURE_READINESS_WINDOWS = {
    "liquidity_20": 20,
    "liquidity_60": 60,
    "liquidity_rank_126": 126,
    "standard_research_252": 252,
    "liquid_v1_listing_age": LIQUID_V1_DEFINITION["listing_age_sessions_min"],
    "momentum_12_1": 273,
    "model_arena_handoff_history": 300,
}
CANDIDATE_RESEARCH_START_DATES = (
    "2011-01-01",
    "2009-01-01",
    "2007-01-01",
    "2006-01-01",
)
CANDIDATE_REFINED_BOUNDARY_SCAN_METHOD = "MONTHLY_SNAPSHOT_BOUNDARIES_WITH_OFFICIAL_SESSION_LOOKBACK"
CANDIDATE_PIT_UNIVERSE_INTERVAL_TYPE = "PIT_UNIVERSE"
CANDIDATE_FEATURE_READINESS_POLICY = "FEATURE_READINESS_REPORTED_SEPARATELY"
CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS = (
    "not_materialized",
    "candidate_start_snapshot_missing",
    "decision_window_snapshots_missing",
)
CANDIDATE_NUMERIC_HARD_FAILURE_KEYS = (
    "identity_failures",
    "instrument_failures",
    "status_failures",
    "session_liquidity_window_failures",
    "price_adjustment_failures",
    "material_missing_factors",
    "contaminating_signal_window_non_pass_boundaries",
)
CANDIDATE_HARD_FAILURE_KEYS = CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS + CANDIDATE_NUMERIC_HARD_FAILURE_KEYS
CANDIDATE_ADVISORY_READINESS_KEYS = (
    "warmup_gate",
)
CANDIDATE_DECISION_GATE_KEYS = (
    "decision_window_gate",
    "session_liquidity_gate",
    "identity_gate",
    "price_action_gate",
    "instrument_gate",
    "status_gate",
)
CANDIDATE_DECISION_REQUIRED_FIELDS = (
    "candidate_start",
    "candidate_audit_status",
    *CANDIDATE_DECISION_GATE_KEYS,
    *CANDIDATE_ADVISORY_READINESS_KEYS,
    "feature_readiness",
    "hard_failures",
    "promotion_interpretation",
)
CANDIDATE_PROMOTION_SUMMARY_FIELDS = (
    "recorded_earliest_candidate_gate_pass_start",
    "earliest_candidate_gate_pass_start",
    "recorded_matches_derived_earliest_candidate_gate_pass_start",
    "candidate_gate_pass_start_dates",
    "candidate_research_ready_start_dates",
    "recorded_refined_earliest_candidate_gate_pass_boundary",
    "refined_earliest_candidate_gate_pass_boundary",
    "recorded_matches_derived_refined_earliest_candidate_gate_pass_boundary",
    "candidate_recommended_pit_universe_interval",
    "candidate_recommended_research_interval",
    "candidate_promotion_decisions",
)
CANDIDATE_PROMOTION_API_METHODS = (
    "candidate_promotion_contract",
    "candidate_promotion_status",
    "candidate_promotion_decision",
    "candidate_promotion_summary",
    "candidate_gate_pass_start_dates",
    "candidate_gate_pass_ready",
    "candidate_pit_universe_ready",
    "candidate_research_ready_start_dates",
    "candidate_research_ready",
    "earliest_candidate_gate_pass_date",
    "refined_earliest_candidate_gate_pass_boundary",
)
CANDIDATE_PASS_VALUE = "PASS"
CANDIDATE_FAIL_VALUE = "FAIL"
CANDIDATE_NOT_RECORDED_VALUE = "NOT_RECORDED"
CANDIDATE_AUDIT_STATUS_VALUES = (CANDIDATE_PASS_VALUE, CANDIDATE_FAIL_VALUE, CANDIDATE_NOT_RECORDED_VALUE)
CANDIDATE_DECISION_GATE_VALUES = (
    CANDIDATE_PASS_VALUE,
    CANDIDATE_FAIL_VALUE,
    "REVIEW_REQUIRED",
    "FAIL_MISSING_FACTORS",
    "FAIL_NON_ORDINARY",
    "FAIL_AMBIGUOUS",
    "NOT_MATERIALIZED",
    CANDIDATE_NOT_RECORDED_VALUE,
)
CANDIDATE_GATE_PASS_INTERPRETATION = "CANDIDATE_GATE_PASS_PENDING_FULL_RELEASE_EVIDENCE"
CANDIDATE_AUDIT_NOT_RECORDED_INTERPRETATION = "AUDIT_NOT_RECORDED"
CANDIDATE_NOT_MATERIALIZED_INTERPRETATION = "NOT_MATERIALIZED"
CANDIDATE_NOT_READY_INTERPRETATION = "NOT_READY"
CANDIDATE_PROMOTION_INTERPRETATION_VALUES = (
    CANDIDATE_GATE_PASS_INTERPRETATION,
    CANDIDATE_AUDIT_NOT_RECORDED_INTERPRETATION,
    CANDIDATE_NOT_MATERIALIZED_INTERPRETATION,
    CANDIDATE_NOT_READY_INTERPRETATION,
)
PARTITIONED_RELEASE_ARTIFACTS = (
    RAW_EXECUTION_PRICE_ARTIFACT,
    ADJUSTED_PRICE_ARTIFACT,
    LIQUIDITY_ARTIFACT,
    ACTIVE_UNIVERSE_ARTIFACT,
)
RESEARCH_MANIFEST_ARTIFACTS = (
    RESEARCH_UNIVERSE_MONTHLY_ARTIFACT,
    REQUIRED_RESEARCH_SECURITY_ARTIFACT,
    LIQUIDITY_ARTIFACT,
    RAW_EXECUTION_PRICE_ARTIFACT,
    ADJUSTED_PRICE_ARTIFACT,
    CORPORATE_ACTIONS_ARTIFACT,
    CORPORATE_ACTION_BOUNDARY_ARTIFACT,
    TRADING_STATUS_INTERVALS_ARTIFACT,
    SUSPENSION_EVENTS_ARTIFACT,
    "unresolved_observed_trading.parquet",
)
REQUIRED_RELEASE_ARTIFACTS = (
    SECURITY_MASTER_ARTIFACT,
    "symbol_history.parquet",
    "security_id_migration.parquet",
    "issuer_master.parquet",
    "listing_episodes.parquet",
    RAW_EXECUTION_PRICE_ARTIFACT,
    ADJUSTED_PRICE_ARTIFACT,
    CORPORATE_ACTIONS_ARTIFACT,
    "trading_status.parquet",
    TRADING_STATUS_INTERVALS_ARTIFACT,
    SUSPENSION_EVENTS_ARTIFACT,
    ACTIVE_UNIVERSE_ARTIFACT,
    "unresolved_observed_trading.parquet",
    LIQUIDITY_ARTIFACT,
    TERMINAL_EVENTS_ARTIFACT,
    DATA_RELEASE_MANIFEST_ARTIFACT,
    TRADING_CALENDAR_ARTIFACT,
    "company_name_history.parquet",
    "isin_history.parquet",
    CORPORATE_ACTION_BOUNDARY_ARTIFACT,
    RESEARCH_UNIVERSE_MONTHLY_ARTIFACT,
    REQUIRED_RESEARCH_SECURITY_ARTIFACT,
    RESEARCH_RELEASE_MANIFEST_ARTIFACT,
    PARTITIONED_ARTIFACTS_MANIFEST,
)
REQUIRED_RESEARCH_REPORTS = (
    "data_source_coverage.md",
    "raw_integrity_audit.md",
    "pre2006_source_reconnaissance.md",
    "research_warmup_coverage.md",
    "research_readiness_by_year.md",
    "early_history_bias_risks.md",
    "pre2013_identity_priority.md",
    "pre2013_identity_episode_audit.md",
    "pre2013_research_identity_promotion.md",
    "manual_price_action_resolution.md",
    "pre2013_adjusted_return_quality.md",
    "pre2013_instrument_classification_audit.md",
    "pre2013_terminal_event_priority.md",
    "pre2013_survivorship_evidence.md",
    "pre2013_research_universe_stability.md",
    "pre2013_historical_universe_counts.md",
    "v2_0_1_regression_comparison.md",
    "v2_0_1_membership_regression_attribution.md",
    "corporate_action_evidence_audit.md",
    "extended_history_research_readiness.md",
    "research_universe_coverage.md",
    "research_identity_priority.md",
    "research_identity_promotion.md",
    "research_price_adjustment_promotion.md",
    "research_universe_corporate_action_audit.md",
    "session_correct_liquidity_audit.md",
    "research_universe_stability.md",
    "survivorship_audit.md",
    "current_survivor_comparison.md",
    "research_scale.md",
)
