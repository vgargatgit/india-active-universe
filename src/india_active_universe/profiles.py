"""Published universe profile contracts."""

TARGET_RELEASE_ID = "india_equity_data_v2.0.0"
PROFILE_ID = "NSE_BROAD_LIQUID_PIT_V1"
PROFILE_VERSION = "LIQUID_V1"
PRIORITY_SCOPE = "LIQUID_V1_OR_HISTORICAL_TOP750"
RESEARCH_START_DATE = "2013-01-01"
RESEARCH_MONTHLY_SNAPSHOT_START = "2013-01-31"
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
TERMINAL_VALUE_POLICY_REQUIREMENT = "DOWNSTREAM_RECOVERY_SENSITIVITY_REQUIRED_WHEN_CANONICAL_TERMINAL_VALUE_UNKNOWN"
DATASET_QUALITY_TIER = "DATASET_EXPLORATORY"
ACTIVE_DEFINITION = "ACTIVE_V1"
PARSER_VERSIONS = {
    "nse_bhavcopy": "nse-bhavcopy-v2",
    "canonicalization": "identity-v1",
}
RESEARCH_HIGH_CONFIDENCE_STATUS = "RESEARCH_HIGH_CONFIDENCE"
RESEARCH_EXPLORATORY_STATUS = "RESEARCH_EXPLORATORY"
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
