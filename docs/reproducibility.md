# Reproducibility

Each release records release ID, build commit field, config hash, raw-source manifest hash, parser versions, artifact hashes, coverage, quality tier, and quality summary. Bulk source manifests use the local file modification time when the original HTTP retrieval timestamp is not available. This limitation is explicit. Same inputs and configuration must produce the same outputs.

For a cached promotion, run `india-equity-data build --source-release releases/india_equity_data_v1.14.0 --release-id india_equity_data_v1.14.1`. The command verifies every parent artifact hash, refuses an existing target, copies Parquet artifacts atomically, and records `build_mode=CACHED_PROMOTION` plus the parent manifest hash. A cached promotion is not a fresh source rebuild.

Release audit is fail-closed. It writes the report before returning a non-zero status when the manifest does not match the release directory or any required artifact is missing.
