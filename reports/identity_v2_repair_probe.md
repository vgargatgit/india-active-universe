# Identity v2 repair probe

This is a narrow rebuild probe, not a promoted release.

Probe window: `2011-04-01` through `2012-08-31`.

Build command:

```text
PYTHONPATH=src .venv/bin/python scripts/build_nse_universe.py --raw data/raw/nse/bhavcopy --out /private/tmp/iau_identity_v2_2011_2012 --start 2011-04-01 --end 2012-08-31 --manual-overrides data/reference/manual_identity_overrides.yaml --canonicalization-version identity-v2
```

Result:

```text
dates=352 observations=501161 unresolved_observations=0 securities=3132 active_rows=494681 findings=0
```

## Key result

`identity-v2` keeps one canonical `security_id` across the no-ISIN to ISIN transition while preserving effective-dated ISIN history.

| Symbol | v2 security_id count | Evidence |
|---|---:|---|
| `HDFCBANK` | 1 | No-ISIN row, `INE040A01018`, and `INE040A01026` map to `SEC_9cb4771e7e7e04a2`. |
| `BHEL` | 1 | No-ISIN row, `INE257A01018`, and `INE257A01026` map to `SEC_3fd66d0c0004b795`. |
| `TATAPOWER` | 1 | No-ISIN row, `INE245A01013`, and `INE245A01021` map to `SEC_8e926dac2a2a0b92`. |

## History continuity spot check

| Symbol | Date | ISIN | history_sessions |
|---|---|---|---:|
| `HDFCBANK` | `2011-06-21` |  | 55 |
| `HDFCBANK` | `2011-06-22` | `INE040A01018` | 56 |
| `BHEL` | `2011-06-21` |  | 55 |
| `BHEL` | `2011-06-22` | `INE257A01018` | 56 |
| `TATAPOWER` | `2011-06-21` |  | 55 |
| `TATAPOWER` | `2011-06-22` | `INE245A01013` | 56 |

## Interpretation

The repair addresses the root cause of the June-2011 collapse for representative large securities.
It does not yet prove the full 2006+ research interval.
A new immutable release must still rebuild prices, adjustments, liquidity, monthly universes, candidate audits, corporate-action boundaries, regression reports, tests, and CI.
