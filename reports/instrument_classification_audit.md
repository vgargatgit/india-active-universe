# Instrument classification audit

Release: `india_equity_data_v1.12.0`

- Ordinary-equity security IDs: 3,422
- ETF security IDs: 362
- Raw observations retained: 7,545,021
- Ordinary-equity active-universe rows: 7,212,493
- Strong ETF markers remaining in ordinary security rows: 0

The classifier promotes only explicit markers such as `ETF`, `BEES`, `LIQUID`, and AMC product names. Prices for classified ETFs remain available in raw and feature artifacts. They are excluded from the ordinary-equity active universe.
