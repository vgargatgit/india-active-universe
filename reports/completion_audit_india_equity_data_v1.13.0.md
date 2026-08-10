# Release completion audit: `india_equity_data_v1.13.0`

## Proven facts

- Coverage: `2006-01-02` through `2026-08-10`.
- Official daily observations: 7,545,021.
- Canonical security-master rows: 4,164.
- Issuers: 3,784.
- Listing episodes: 3,784.
- Corporate-action rows: 39,185.
- Terminal-event rows: 1,903.
- Status intervals: 5,145.
- Suspended intervals: 2.
- Status interval overlaps: 0.
- Adjusted-price quality counts: `{'RAW_ONLY': 4278431, 'PRICE_ACTION_ADJUSTED': 54284, 'PARTIALLY_ADJUSTED': 3212306}`.
- Corporate-action boundary validation: `{'MISSING_BOUNDARY_PRICE': 49, 'PASS': 470, 'WARNING_LARGE_BOUNDARY_MOVE': 44}`.

## Required artifact checks

- PASS: `security_master.parquet`
- PASS: `symbol_history.parquet`
- PASS: `issuer_master.parquet`
- PASS: `listing_episodes.parquet`
- PASS: `daily_prices_raw.parquet`
- PASS: `daily_prices_adjusted.parquet`
- PASS: `corporate_actions.parquet`
- PASS: `trading_status.parquet`
- PASS: `active_universe_daily.parquet`
- PASS: `liquidity_features.parquet`
- PASS: `terminal_events.parquet`
- PASS: `data_release_manifest.json`
- PASS: `trading_calendar.parquet`

## Explicit limitations

- The release is exploratory, not confirmatory-ready.
- Scanned delisting notices require external OCR tooling and remain evidence-only.
- Many terminal-event identities, merger events, insolvency outcomes, and terminal values remain unresolved.
- Cash-dividend and total-return adjustment coverage is partial.
- Historical sector and market-cap PIT data are not fabricated.
