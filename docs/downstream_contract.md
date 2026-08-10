# Downstream contract

Consumers must pin a release ID and manifest hash, then read published artifacts only: `security_master`, `symbol_history`, `issuer_master`, `listing_episodes`, `daily_prices_raw`, `daily_prices_adjusted`, `corporate_actions`, `trading_status`, `active_universe_daily`, `liquidity_features`, and `terminal_events`.

The stable interfaces are `resolve_symbol(symbol, as_of_date)`, `history(security_id, start, end)`, `active_on(as_of_date)`, `eligible_on(as_of_date, ...)`, `ranked_liquid_on(as_of_date, n, metric=...)`, and `status_on(as_of_date)`. `DataPlatform.from_release()` reads the published security master and queries Parquet prices, universe, liquidity, and effective-dated status data. Status queries return `ACTIVE_TRADING`, `SUSPENDED`, `DELISTED`, or `UNKNOWN_STATUS` intervals with evidence quality. Strict mode rejects requests outside trusted component coverage.
