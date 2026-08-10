# Session-correct liquidity audit

Liquidity windows use official NSE session positions from `trading_calendar.parquet`.

- Window definitions: 20, 60, 126, and 252 official sessions.
- Positive-volume days count only observed rows with volume greater than zero.
- Zero-volume days count observed rows with zero or null volume.
- Absent-observation days count official sessions with no security row.
- Maximum absent-observation count in the monthly research artifact: `59`.
- Ranking metric: trailing 126-session median traded value.

The feature artifact contains `liquidity_window_definition = OFFICIAL_NSE_SESSION_WINDOW`.
Weekend and holiday dates are not part of any window.
