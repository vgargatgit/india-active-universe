# Pricing model

Canonical raw prices preserve exchange nominal values: raw OHLC, volume, traded value, source, and quality. Adjusted prices are separate datasets and never overwrite raw history. Release `india_equity_data_v2.0.0` keeps canonical single-file Parquet artifacts for compatibility and adds year-partitioned sidecar datasets for large raw, adjusted, liquidity, and active-universe tables. Both layouts remain DuckDB-friendly.
