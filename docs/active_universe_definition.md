# Active universe definition

`ACTIVE_V1` is the set of ordinary NSE `EQ` securities with a valid qualifying official exchange trading record on date T. It is not an index and is not forced to a fixed count. Suspended, delisted, no-trade, missing-source, and unknown conditions remain distinguishable.

Investability is a downstream profile. A sample `LIQUID_V1` profile may require price >= 20, at least 272 prior valid sessions, at least 40 positive-volume observations in the trailing 60 sessions, and 60-session median traded value >= 5,000,000. Thresholds are not canonical.

The release API joins PIT liquidity features lazily when reading `active_universe_daily.parquet`. Features include listing age, 20/60/126/252-session traded-value statistics, stale-price counts, and date-level liquidity quintiles. Consumers can call `eligible_on(as_of_date, ...)` or `ranked_liquid_on(as_of_date, n, metric=...)`; the default ranking metric is trailing 126-session median traded value and ranking is not index membership.

Status intervals are separate from active snapshots. `ACTIVE_TRADING` requires an observed qualifying record; `DELISTED` requires linked official evidence; `UNKNOWN_STATUS` means the observation history ended before coverage end and does not imply suspension or zero recovery.
