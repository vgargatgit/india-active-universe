# Survivorship guarantee

Historical membership is discovered from historical exchange observations. For any date T, no listing after T can appear, no future symbol mapping is needed to infer membership, and liquidity/history features use data <= T. A security that later disappears remains in earlier active snapshots. This repository does not use current constituents or NIFTY 500 membership.

`scripts/validate_pit.py` exercises future-listing, future-liquidity, symbol rename/reuse, historical dead-security, and future-corporate-action cases.
