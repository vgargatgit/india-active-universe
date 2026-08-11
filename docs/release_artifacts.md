# Release artifacts

Published releases contain Parquet artifacts named `security_master.parquet`, `symbol_history.parquet`, `issuer_master.parquet`, `listing_episodes.parquet`, `daily_prices_raw.parquet`, `daily_prices_adjusted.parquet`, `corporate_actions.parquet`, `trading_status.parquet`, `trading_status_intervals.parquet`, `active_universe_daily.parquet`, `liquidity_features.parquet`, `terminal_events.parquet`, and `data_release_manifest.json`.

The publisher uses Zstandard compression and batch writes. Large price/universe artifacts should be partitioned by year when promoted to the long-term release layout; the initial single-file artifact remains DuckDB-readable and is produced without mutating the JSONL build intermediates.

Release `india_equity_data_v2.0.0` publishes the full contract plus `company_name_history.parquet`, `isin_history.parquet`, `trading_calendar.parquet`, `trading_status_intervals.parquet`, `suspension_events_resolved.parquet`, `research_universe_monthly.parquet`, `required_research_security.parquet`, `research_release_manifest.json`, and the scoped research reports. Its calendar contains only dates supported by official NSE market-data files. Its `liquidity_features.parquet` uses official 20/60/126/252-session windows and includes positive, zero-volume, and absent-observation counts. Its adjusted-price artifact remains separate from raw nominal prices. Explicit ETF markers are excluded from ordinary-equity research snapshots. Status intervals are non-overlapping. Unknown intervals are evidence gaps, never silently labeled suspension or delisting.

`reports/data_source_coverage.md` compares valid source-manifest dates with the published observation-derived calendar. It verifies archive integrity, not an independent exchange holiday calendar.
