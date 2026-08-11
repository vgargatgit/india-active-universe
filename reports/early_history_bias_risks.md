# Early-history bias risks

This report is evidence-backed. `not available` means the current release artifacts do not yet contain that evidence.

| Risk | Evidence | Current interpretation |
|---|---|---|
| Left-censoring | `707` securities first appear on the first observed source date `2004-01-01`. | These securities must not be treated as IPOs solely because source coverage starts there. |
| Pre-2006 market-data availability | `4` valid representative archives out of `4` probed. | Pre-2006 warmup may be feasible, pending bulk integrity checks. |
| Missing ISIN in early required scope | `1507` pre-2013 required securities lack ISIN in monthly snapshots. | Missing ISIN can still allow `RECONSTRUCTED_TRADING_IDENTITY`, but ticker reuse and continuity checks must pass. |
| Early identity failures | `0` pre-2013 required securities fail research identity in monthly snapshots. | Any promoted interval must reduce required-scope identity failures to zero. |
| Early liquidity sparsity | Maximum pre-2013 `absent_observation_days_60`: `59`. | Sparse rows are counted through official-session windows, not ignored. |
| Signal warmup | `14471` pre-2013 monthly rows are not ready for 273-session momentum-style history. | Universe eligibility is separate from model/signal readiness. |
| Left-boundary price-action validation | `73` material boundary validations lack pre-event observations or are left-censored. | These are not PASS; they require contamination analysis before promotion. |
| Early monthly artifact coverage | `99375` rows, `1965` securities, `1597` required-scope securities before `2013-01-01`. | Zero values mean early candidate snapshots have not yet been materialized into this release. |
| Market-cap and sector history | not available in release artifacts | These must not be backfilled from current classifications. |

This report does not promote any early interval.
Promotion still requires source integrity, warmup readiness, session liquidity, identity, instrument, material price-action, PIT invariant, CI, and test gates.
