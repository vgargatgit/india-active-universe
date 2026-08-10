# Release completion audit: `india_equity_data_v2.0.0`

## Proven facts

- Coverage: `2006-01-02` through `2026-08-10`.
- Official daily observations: 7,545,021.
- Canonical security-master rows: 6,235.
- Issuers: 5,745.
- Listing episodes: 5,745.
- Corporate-action rows: 39,185.
- Terminal-event rows: 1,903.
- Status intervals: 9,062.
- Suspended intervals: 0.
- Status interval overlaps: 0.
- Adjusted-price quality counts: `{"PARTIALLY_ADJUSTED": 2770915, "PRICE_ACTION_ADJUSTED": 167119, "RAW_ONLY": 4606987}`.
- Corporate-action boundary validation: `{"MISSING_BOUNDARY_PRICE": 691, "PASS": 512, "WARNING_LARGE_BOUNDARY_MOVE": 75}`.

## Required artifact checks

- PASS: `security_master.parquet`
- PASS: `symbol_history.parquet`
- PASS: `issuer_master.parquet`
- PASS: `listing_episodes.parquet`
- PASS: `daily_prices_raw.parquet`
- PASS: `daily_prices_adjusted.parquet`
- PASS: `corporate_actions.parquet`
- PASS: `trading_status.parquet`
- PASS: `trading_status_intervals.parquet`
- PASS: `active_universe_daily.parquet`
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

## Explicit limitations

- The release is exploratory, not confirmatory-ready.
- Scanned delisting notices require external OCR tooling and remain evidence-only.
- Many terminal-event identities, merger events, insolvency outcomes, and terminal values remain unresolved.
- Cash-dividend and total-return adjustment coverage is partial.
- Historical sector and market-cap PIT data are not fabricated.
