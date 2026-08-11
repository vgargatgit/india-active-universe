# Architecture

The pipeline is strictly layered: immutable `RAW` source files -> source-specific `NORMALIZED` tables -> resolved `CANONICAL` identities and observations -> `DERIVED` adjusted prices, status, features, and universes. Canonical interpretation may improve without mutating raw evidence.

The first implementation targets dated NSE bhavcopy/security reference inputs and keeps BSE as corroborating identity/terminal-event evidence. Each row carries source file ID, SHA256, parser version, and canonicalization version.

All point-in-time transformations take an explicit as-of date and may only use observations and events available on or before that date, subject to the documented research-adjustment convention.

The source-driven normalization stage is bounded by `--start` and `--end`. For example, `india-equity-data normalize-market-data --start 2006-01-01 --end 2006-12-31` reads only matching immutable NSE bhavcopy files and writes non-raw intermediates. An empty or invalid range fails instead of producing a partial success.

The current NSE source adapter builds identity rows, raw prices, active snapshots, and liquidity features as one coupled pass. The CLI exposes these as separate names for pipeline compatibility, but each name runs the same deterministic core pass and does not imply an independent source transformation.

`india-equity-data build --start ... --end ...` runs this source-driven pass from the immutable cache and creates intermediates only. It does not publish a release. Release publication requires a verified parent release or a future complete source-release adapter.

`india-equity-data build-source-release --release-id ... --terminal-events ... --suspension-events ... --ci-run-id ...` is the fresh source-release adapter. It requires explicit terminal-event, suspension-status, source-manifest, manual-override, and CI evidence, creates a separate build workspace, publishes Parquet artifacts, writes the release manifest, and runs the completion audit. Use `--ci-status-report` instead of `--ci-run-id` when a previously captured `ci_status_<release_id>.json` file must be reused. It does not invent terminal values.

`india-equity-data candidate-readiness --release-id ...` is a read-only release inspection command. Without `--candidate-start`, it prints the candidate promotion summary. With `--candidate-start 2006-01-01`, it prints the row-level candidate decision, gate-pass readiness, research-quality status, and strict research-ready status for that configured start.

Observations without one dated identity are not discarded. They are written to `data/canonical/unresolved_observed_trading.jsonl` with raw OHLCV, source hashes, candidate IDs, and an `UNRESOLVED` status. They cannot enter the canonical active universe until identity review resolves them.
