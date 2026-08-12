# Release completion audit: `india_equity_data_v2.2.8`

## Proven facts

- Coverage: `2004-01-01` through `2026-08-10`.
- Official daily observations: 7,914,924.
- Canonical security-master rows: 6,362.
- Issuers: 3,969.
- Listing episodes: 3,969.
- Corporate-action rows: 39,185.
- Terminal-event rows: 1,903.
- Status intervals: 5,510.
- Suspended intervals: 0.
- Status interval overlaps: 0.
- Adjusted-price quality counts: `{"TOTAL_RETURN_PARTIAL": 7914924}`.
- Adjusted-price contract missing columns: `[]`.
- Liquidity feature rows with non-official session window: 0.
- Corporate-action boundary validation: `{"ADVISORY_BOUNDARY_DRIFT": 31, "NO_LOCAL_BOUNDARY_OBSERVATION": 42, "NO_POST_EVENT_OBSERVATION": 75, "NO_PRE_EVENT_OBSERVATION": 73, "PASS": 1056, "WARNING_LARGE_BOUNDARY_MOVE": 2}`.
- Unresolved required material price-action boundaries: 39.
- RAW integrity validation: `{"status": "PASS"}`.
- Source coverage validation: `{"status": "PASS"}`.
- Research invariant validation: `{"failure_count": 0, "failures": {}, "missing_metrics": [], "status": "PASS"}`.
- Candidate promotion audits: `{"candidate_count": 4, "duplicate_candidate_starts": [], "malformed_candidate_audits": [], "malformed_candidate_report": [], "missing_candidate_starts": [], "unexpected_candidate_starts": []}`.
- Test results: `{"early_model_arena_handoff_passed": true, "errors": 0, "failures": 0, "model_arena_handoff_passed": true, "multi_era_source_fixture_passed": true, "skipped": 0, "tests": 118}`.
- GitHub Actions CI: `{"conclusion": "success", "descends_from_release_git_commit": true, "failed_jobs": [], "head_sha": "2cc631b3dcaa4f8c9f132163d31414ca12c029d6", "job_count": 0, "matches_release_git_commit": true, "release_git_commit": "2cc631b3dcaa4f8c9f132163d31414ca12c029d6", "run_id": 31562683887, "run_url": "https://github.com/vgargatgit/india-active-universe/actions/runs/31562683887", "status": "completed", "workflow_name": "ci"}`.
- Partitioned sidecar layout: `{"artifact_count": 4, "failed_artifacts": [], "file_count": 92, "layout": "YEAR_PARTITIONED_SIDECAR_V1", "missing_required_artifacts": [], "partitioned_artifacts": ["daily_prices_raw.parquet", "daily_prices_adjusted.parquet", "liquidity_features.parquet", "active_universe_daily.parquet"], "status": "PASS"}`.

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

## Explicit limitations

- The complete 2006 onward archive is exploratory unless covered by a manifest research-quality interval; the scoped `2006-01-31` onward research universe is RESEARCH_HIGH_CONFIDENCE.
- Scanned delisting notices require external OCR tooling and remain evidence-only.
- Many terminal-event identities, merger events, insolvency outcomes, and terminal values remain unresolved.
- Cash-dividend and total-return adjustment coverage is partial.
- Historical sector and market-cap PIT data are not fabricated.
