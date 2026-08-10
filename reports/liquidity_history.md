# Liquidity history

The release liquidity table is built with DuckDB window functions over official raw Parquet prices. It contains PIT 20, 60, 126, and 252-session valid-day, median, and average traded-value fields; listing age; stale-price counts; and date-level 60-session liquidity quintiles. All windows end on the feature date. No future observation enters a feature.
