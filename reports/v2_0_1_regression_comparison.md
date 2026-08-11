# v2.0.1 regression comparison

Baseline release: `releases/india_equity_data_v2.0.1`.
Candidate release: `releases/india_equity_data_v2.1.1`.
Comparison interval: `2013-01-01` through `2026-08-10`.

| Check | Difference rows |
|---|---:|
| Monthly universe counts | 135 |
| LIQUID_V1 membership | 140 |
| Top-750 membership | 370 |
| Signal price series | 0 |
| Material corporate-action factors | 50 |

## Difference interpretation

- Candidate-only `LIQUID_V1` membership differences: `0`.
- Baseline-only monthly rows explained by excluded non-ordinary symbols containing `GOLD` or `NIFTY`: `658` of `658`.
- Existing material corporate-action factor value changes: `0`.
- Baseline-only `LIQUID_V1` symbols removed by the ordinary-equity scope correction:

| Symbol | Difference rows |
|---|---:|
| `KOTAKGOLD` | 68 |
| `GOLDSHARE` | 47 |
| `RELGOLD` | 23 |
| `AXISGOLD` | 2 |

A non-zero Top-750 membership difference is expected when baseline non-ordinary instruments are removed: the PIT rank cutoff admits replacement ordinary-equity names without changing signal prices.
Candidate-only official corporate-action rows are not treated as 2013+ regressions when existing material factor values are unchanged and the signal price series diff is zero.

Regression status: `PASS_WITH_JUSTIFIED_SCOPE_CORRECTION`.
