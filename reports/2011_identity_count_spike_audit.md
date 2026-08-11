# 2011 identity count spike audit

Release inspected: `releases/india_equity_data_v2.1.1`.
Window: `2011-04-01` through `2012-08-31`.

## Finding

The active-ordinary count spike is explained by duplicated generated security IDs, not by a doubled investable market.
In 2011, the same symbol population is split between no-ISIN and ISIN-backed security IDs.

| year | active ordinary security IDs | unique symbols | unique ISINs | no-ISIN security IDs | ISIN security IDs | ID minus symbol count | fragmented symbols |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `2011` | `3012` | `1551` | `1540` | `1472` | `1540` | `1461` | `1460` |
| `2012` | `1561` | `1567` | `1561` | `0` | `1561` | `-6` | `10` |

## Release blocker

The count spike must become a hard promotion blocker until canonical continuity removes source-format fragmentation or explicitly classifies true security changes.
