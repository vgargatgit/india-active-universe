# Adjustment quality

Release `india_equity_data_v1.9.0` applies 866 unambiguous official price-action factors: 712 bonus factors and 154 face-value split factors. They affect 558,862 daily rows. Official cash amounts are parsed for 18,354 dividend events, and 3,212,306 rows have an ex-date-close-based total-return factor. The total-return series is labelled `PARTIALLY_ADJUSTED` because unresolved events remain. Price-return and total-return columns remain separate.
