# Release completion audit: `india_equity_data_v2.2.4`

## Required artifact checks

- PASS: `security_master.parquet`
- PASS: `symbol_history.parquet`
- PASS: `security_id_migration.parquet`
- PASS: `issuer_master.parquet`
- PASS: `listing_episodes.parquet`
- PASS: `daily_prices_raw.parquet`
- PASS: `daily_prices_adjusted.parquet`
- PASS: `corporate_actions.parquet`
- PASS: `trading_status.parquet`
- PASS: `trading_status_intervals.parquet`
- PASS: `suspension_events_resolved.parquet`
- PASS: `active_universe_daily.parquet`
- PASS: `unresolved_observed_trading.parquet`
- PASS: `liquidity_features.parquet`
- PASS: `terminal_events.parquet`
- PASS: `data_release_manifest.json`
- PASS: `trading_calendar.parquet`
- PASS: `company_name_history.parquet`
- PASS: `isin_history.parquet`
- PASS: `corporate_action_boundary_validation.parquet`
- PASS: `research_universe_monthly.parquet`
- PASS: `required_research_security.parquet`
- PASS: `research_release_manifest.json`
- PASS: `partitioned_artifacts_manifest.json`

- FAIL: research quality is not RESEARCH_HIGH_CONFIDENCE
- FAIL: data manifest research_coverage.research_verified_start is not one of ['2006-01-01', '2007-01-01', '2009-01-01', '2011-01-01', '2013-01-01']
- FAIL: research_quality.status is not RESEARCH_HIGH_CONFIDENCE
