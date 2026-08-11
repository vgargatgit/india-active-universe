# Pre-2013 historical universe counts

Counts are derived from historical monthly PIT snapshots before the current research control start.
They are not index membership and are not forced to 500 securities.

| Year | Active ordinary | Fully seasoned observed history | 300-session ready | LIQUID_V1 | Top-500 | Top-750 | Top-1000 | Required scope | 252-signal ready | 273-signal ready |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2006 | 1071 | 844 | 805 | 454 | 680 | 958 | 1071 | 958 | 840 | 819 |
| 2007 | 1228 | 952 | 910 | 507 | 697 | 975 | 1210 | 976 | 961 | 933 |
| 2008 | 1322 | 1153 | 1111 | 540 | 664 | 934 | 1234 | 934 | 1155 | 1130 |
| 2009 | 1346 | 1257 | 1218 | 576 | 629 | 943 | 1269 | 943 | 1240 | 1234 |
| 2010 | 1494 | 1288 | 1258 | 742 | 691 | 952 | 1234 | 964 | 1287 | 1272 |
| 2011 | 1589 | 1384 | 1358 | 598 | 632 | 911 | 1162 | 911 | 1384 | 1373 |
| 2012 | 1564 | 1488 | 1427 | 569 | 621 | 899 | 1155 | 899 | 1465 | 1450 |

`Fully seasoned observed history` uses observed sessions only. Left-censored securities can have older true listing age but still lack pre-source price history.
`Required scope` is `LIQUID_V1_OR_HISTORICAL_TOP750`; low-liquidity names outside that scope do not block early promotion.
