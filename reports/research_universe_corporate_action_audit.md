# Research universe corporate-action audit

Material price actions are `SPLIT`, `REVERSE_SPLIT`, and `BONUS`.

| Event type | Events | Missing factors |
|---|---:|---:|
| `BONUS` | 544 | 0 |
| `REVERSE_SPLIT` | 2 | 0 |
| `SPLIT` | 437 | 0 |

Material events with missing price/share factors: `0`.
Promotion gate: `PASS`.

## Boundary validation in the required scope

| Boundary status | Distinct events |
|---|---:|
| `MISSING_BOUNDARY_PRICE` | 244 |
| `PASS` | 411 |
| `WARNING_LARGE_BOUNDARY_MOVE` | 55 |

A missing boundary price means that the adjacent official price is unavailable for continuity validation. It does not change the official factor or raw price. These cases remain explicit limitations.

Rows remain traceable to `corporate_actions.parquet`; this report does not alter raw nominal prices.
