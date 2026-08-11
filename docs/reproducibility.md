# Reproducibility

Each release records release ID, build commit field, config hash, raw-source manifest hash, parser versions, artifact hashes, coverage, quality tier, and quality summary. Bulk source manifests use the local file modification time when the original HTTP retrieval timestamp is not available. This limitation is explicit. Same inputs and configuration must produce the same outputs.

For Phase 2, release `india_equity_data_v2.0.0` must be built from the current source pipeline. Do not use a cached promotion from an older release as a substitute. The source build records the actual Git commit, source manifest hash, manual override hash, config hash, parser versions, artifact hashes, test result hash, CI status hash, and quality report hashes.

Release audit is fail-closed. It writes the report before returning a non-zero status when the manifest does not match the release directory, a required artifact is missing, or a published artifact hash differs from the manifest.
