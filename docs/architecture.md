# Architecture

The pipeline is strictly layered: immutable `RAW` source files -> source-specific `NORMALIZED` tables -> resolved `CANONICAL` identities and observations -> `DERIVED` adjusted prices, status, features, and universes. Canonical interpretation may improve without mutating raw evidence.

The first implementation targets dated NSE bhavcopy/security reference inputs and keeps BSE as corroborating identity/terminal-event evidence. Each row carries source file ID, SHA256, parser version, and canonicalization version.

All point-in-time transformations take an explicit as-of date and may only use observations and events available on or before that date, subject to the documented research-adjustment convention.
