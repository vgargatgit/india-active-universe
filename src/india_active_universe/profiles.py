"""Published universe profile contracts."""

PROFILE_ID = "NSE_BROAD_LIQUID_PIT_V1"
PROFILE_VERSION = "LIQUID_V1"
PRIORITY_SCOPE = "LIQUID_V1_OR_HISTORICAL_TOP750"

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
