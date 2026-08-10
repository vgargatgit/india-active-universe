# Architecture

The pipeline is strictly layered: immutable `RAW` source files -> source-specific `NORMALIZED` tables -> resolved `CANONICAL` identities and observations -> `DERIVED` adjusted prices, status, features, and universes. Canonical interpretation may improve without mutating raw evidence.

The first implementation targets dated NSE bhavcopy/security reference inputs and keeps BSE as corroborating identity/terminal-event evidence. Each row carries source file ID, SHA256, parser version, and canonicalization version.

All point-in-time transformations take an explicit as-of date and may only use observations and events available on or before that date, subject to the documented research-adjustment convention.

The source-driven normalization stage is bounded by `--start` and `--end`. For example, `india-equity-data normalize-market-data --start 2006-01-01 --end 2006-12-31` reads only matching immutable NSE bhavcopy files and writes non-raw intermediates. An empty or invalid range fails instead of producing a partial success.

The current NSE source adapter builds identity rows, raw prices, active snapshots, and liquidity features as one coupled pass. The CLI exposes these as separate names for pipeline compatibility, but each name runs the same deterministic core pass and does not imply an independent source transformation.
