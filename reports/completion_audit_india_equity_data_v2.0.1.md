# Release completion audit: `india_equity_data_v2.0.1`

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
- Adjusted-price quality counts: `{"TOTAL_RETURN_PARTIAL": 7545021}`.
- Corporate-action boundary validation: `{"NO_LOCAL_BOUNDARY_OBSERVATION": 25, "NO_POST_EVENT_OBSERVATION": 349, "NO_PRE_EVENT_OBSERVATION": 341, "PASS": 529, "WARNING_LARGE_BOUNDARY_MOVE": 31}`.
- Test results: `{"errors": 0, "failures": 0, "model_arena_handoff_passed": true, "skipped": 0, "tests": 25}`.

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
- PASS: `suspension_events_resolved.parquet`
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

- The complete 2006 onward archive is exploratory; the scoped 2013 onward research universe is RESEARCH_HIGH_CONFIDENCE.
- Scanned delisting notices require external OCR tooling and remain evidence-only.
- Many terminal-event identities, merger events, insolvency outcomes, and terminal values remain unresolved.
- Cash-dividend and total-return adjustment coverage is partial.
- Historical sector and market-cap PIT data are not fabricated.
