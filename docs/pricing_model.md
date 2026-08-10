# Pricing model

Canonical raw prices preserve exchange nominal values: raw OHLC, volume, traded value, source, and quality. Adjusted prices are separate datasets and never overwrite raw history. Parquet outputs should be partitioned by year (or year/month) and remain DuckDB-friendly.
