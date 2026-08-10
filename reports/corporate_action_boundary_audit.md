# Corporate-action boundary audit

Release: `india_equity_data_v1.11.0`

The audit checks identity-resolved official `SPLIT`, `REVERSE_SPLIT`, and `BONUS` events. It compares the last raw close before the ex-date with the first raw close on or after the ex-date after applying the share factor.

- Events checked: 563
- `PASS`: 470
- `WARNING_LARGE_BOUNDARY_MOVE`: 44
- `MISSING_BOUNDARY_PRICE`: 49

Warnings are retained as quality findings. Raw observations are never removed or rewritten. A warning can represent a genuine market move, a compound corporate action, a missing price, or an incorrect source/event interpretation.
