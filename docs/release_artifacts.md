# Release artifacts

Published releases contain Parquet artifacts named `security_master.parquet`, `symbol_history.parquet`, `issuer_master.parquet`, `listing_episodes.parquet`, `daily_prices_raw.parquet`, `daily_prices_adjusted.parquet`, `corporate_actions.parquet`, `trading_status.parquet`, `active_universe_daily.parquet`, `liquidity_features.parquet`, `terminal_events.parquet`, and `data_release_manifest.json`.

The publisher uses Zstandard compression and batch writes. Large price/universe artifacts should be partitioned by year when promoted to the long-term release layout; the initial single-file artifact remains DuckDB-readable and is produced without mutating the JSONL build intermediates.

Release `india_equity_data_v1.1.0` publishes the full contract plus `trading_status_intervals.parquet`, `delisting_notice_inventory.parquet`, `suspension_notice_evidence.parquet`, `source_manifest.json`, and `suspension_source_manifest.json`. Unknown intervals are evidence gaps, never silently labeled suspension or delisting. Notice and suspension rows are evidence-review records, not canonical terminal events, until dated identity resolution is complete.
