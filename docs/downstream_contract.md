# Downstream contract

Consumers must pin a release ID and manifest hash, then read published artifacts only: `security_master`, `symbol_history`, `issuer_master`, `listing_episodes`, `daily_prices_raw`, `daily_prices_adjusted`, `corporate_actions`, `trading_status`, `active_universe_daily`, `liquidity_features`, and `terminal_events`.

The stable interfaces are `resolve_symbol(symbol, as_of_date)`, `history(security_id, start, end)`, `active_on(as_of_date)`, and `eligible_on(as_of_date, ...)`. `DataPlatform.from_release()` reads the published security master and lazily queries Parquet prices/universe data. Strict mode rejects requests outside trusted component coverage.
