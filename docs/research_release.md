# Research release contract

The promoted profile is `NSE_BROAD_LIQUID_PIT_V1` with profile version `LIQUID_V1`.

The profile requires ordinary NSE equity, active trading status, price at least INR 20, listing age at least 272 official sessions, at least 40 positive-volume observations in the last 60 official NSE sessions, and trailing 60-session median traded value of at least INR 5,000,000.

The monthly snapshot is `research_universe_monthly.parquet`. The Top-500, Top-750, and Top-1000 fields are PIT liquidity diagnostics over ordinary active equities. They are not index membership.

Consumer profile rows carry `profile_id`, `profile_version`, `as_of_date`, `eligibility_result`, and `eligibility_reason_codes`. A selected LIQUID_V1 row has `eligibility_result=ELIGIBLE` and `eligibility_reason_codes=PASSED_LIQUID_V1`. Excluded monthly rows carry the first failed profile rule where available.

Use:

- `daily_prices_raw.parquet` for nominal execution prices.
- `daily_prices_adjusted.parquet` for price-return research, subject to its row quality.
- `liquidity_features.parquet` for official-session PIT features.
- `research_release_manifest.json` for scope, quality, hashes, and limitations.

The full archive includes 2006 onward. The research quality boundary starts in 2013. Strict API reads use the scoped research interval from `research_release_manifest.json` when it declares `RESEARCH_HIGH_CONFIDENCE`. Unknown terminal values remain downstream recovery scenarios.
