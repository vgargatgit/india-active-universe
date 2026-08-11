# india-active-universe

Independent historical Indian cash-equity data foundation. This project reconstructs a point-in-time NSE cash-equity universe from historical exchange observations; it does not reconstruct index membership and contains no trading strategy logic.

## Scope

- Primary market: NSE cash equities, initially series `EQ`.
- Target coverage: 2006 onward where official NSE data is available.
- Outputs: versioned security identity, raw and adjusted prices, trading status, active-universe snapshots, liquidity features, terminal events, provenance, and quality reports.

Historical existence is discovered from official dated market observations, not from a current security list. Securities that later delist, merge, fail, or change symbols remain available for dates on which they traded.

## Layers

`data/raw` is immutable and hashed. `data/normalized` is source-specific normalization. `data/canonical` contains resolved identities and raw observations. `data/derived` contains adjustments, features, and universe snapshots. Large datasets are intentionally excluded from ordinary Git.

## Quick start

```bash
python -m pip install -e '.[dev]'
india-equity-data --help
```

The current research release is `india_equity_data_v2.0.1`: official NSE observations from 2006-01-02 through 2026-08-10, fresh source-built Parquet artifacts, official-session liquidity windows, effective-dated identities, raw and price-return adjusted prices, explicit status and terminal-event records, and a monthly `NSE_BROAD_LIQUID_PIT_V1` snapshot for 2013 onward. `LIQUID_V1` is a versioned consumer profile. It is not NIFTY 500 membership and it is not strategy logic. The full archive remains exploratory; the bounded liquid research scope is separately quality-labeled in `research_release_manifest.json`.

Published release artifacts are compressed Parquet. JSONL files under `data/` are build intermediates and audit/debug outputs, not the downstream storage contract.

To create a fresh release, use `PYTHONPATH=src .venv/bin/python scripts/build_source_release.py --release-id <new-release> --terminal-events releases/india_equity_data_v1.14.1/terminal_events.parquet --start 2006-01-02 --end <last-session>`. A cached promotion is not a substitute for this source rebuild.

For monthly research consumption, use `platform.profile_on("2018-03-29", "LIQUID_V1")` and record the release ID and manifest hash. Use raw nominal OHLC for execution and the price-return adjusted close for signals.

## Independence

This repository has no dependency on `vgargatgit/india500-alpha-lab`, NIFTY 500 membership, index constituents, strategy code, or future-performance labels.

See [docs/survivorship_guarantee.md](docs/survivorship_guarantee.md) and [docs/downstream_contract.md](docs/downstream_contract.md).
