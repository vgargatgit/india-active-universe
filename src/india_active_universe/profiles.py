"""Published universe profile contracts."""

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
LIQUIDITY_ARTIFACT = "liquidity_features.parquet"
TERMINAL_VALUE_POLICY_REQUIREMENT = "DOWNSTREAM_RECOVERY_SENSITIVITY_REQUIRED_WHEN_CANONICAL_TERMINAL_VALUE_UNKNOWN"
DATASET_QUALITY_TIER = "DATASET_EXPLORATORY"
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
RESEARCH_MANIFEST_ARTIFACTS = (
    "research_universe_monthly.parquet",
    "required_research_security.parquet",
    LIQUIDITY_ARTIFACT,
    RAW_EXECUTION_PRICE_ARTIFACT,
    "daily_prices_adjusted.parquet",
    "corporate_actions.parquet",
    "corporate_action_boundary_validation.parquet",
    "trading_status_intervals.parquet",
    "suspension_events_resolved.parquet",
    "unresolved_observed_trading.parquet",
)
