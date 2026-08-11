# Pre-2013 research identity promotion

Scope: `LIQUID_V1_OR_HISTORICAL_TOP750`.
Current control start: `2013-01-01`.

Each row applies the existing research identity gate to required securities from the candidate start through the day before the current control start.

| Candidate start | First scoped month | Last scoped month | Required securities | RECONSTRUCTED_TRADING_IDENTITY | Other accepted identities | Identity failures | Hard gate |
|---|---|---|---:|---:|---:|---:|---|
| 2011-01-01 | 2011-01-31 | 2012-12-31 | 1004 | 68 | 936 | 0 | `PASS` |
| 2009-01-01 | 2009-01-30 | 2012-12-31 | 1249 | 154 | 1095 | 0 | `PASS` |
| 2007-01-01 | 2007-01-31 | 2012-12-31 | 1442 | 251 | 1191 | 0 | `PASS` |
| 2006-01-01 | 2006-01-31 | 2012-12-31 | 1597 | 343 | 1254 | 0 | `PASS` |

Hard gate: zero required-scope identity failures for the candidate interval.
`NOT_MATERIALIZED` means the current release does not yet contain monthly candidate snapshots for that interval.
A `PASS` here is necessary but not sufficient; promotion also requires source, warmup, instrument, price-action, PIT invariant, regression, test, and CI gates.
