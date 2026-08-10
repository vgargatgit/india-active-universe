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

The current materialized release is `india_equity_data_v1.14.0`: official NSE observations, effective-dated company-name and ISIN histories, an official-observation trading calendar, conservative instrument classification, corporate actions with split, bonus, and cash-dividend fields, separate price-return and partial total-return prices, full PIT liquidity features, delisting evidence inventory, resolved suspension evidence, non-overlapping effective-dated status intervals, corporate-action boundary findings, and raw-source manifests from 2006-01-02 through 2026-08-10, published as compressed Parquet. Nullable terminal-event value fields use a stable schema. Identity and event quality remain date- and field-specific; unresolved cases are explicit. This is an exploratory release. It is not a claim that all suspensions, terminal events, or adjusted returns are resolved.

Published release artifacts are compressed Parquet. JSONL files under `data/` are build intermediates and audit/debug outputs, not the downstream storage contract.

To create an immutable cached promotion, use `india-equity-data build --source-release releases/india_equity_data_v1.14.0 --release-id india_equity_data_v1.14.1`. The command verifies parent hashes and records the parent release. It does not claim to re-download or re-parse source files.

## Independence

This repository has no dependency on `vgargatgit/india500-alpha-lab`, NIFTY 500 membership, index constituents, strategy code, or future-performance labels.

See [docs/survivorship_guarantee.md](docs/survivorship_guarantee.md) and [docs/downstream_contract.md](docs/downstream_contract.md).
