# Pre-2013 historical universe counts

Counts are derived from historical monthly PIT snapshots before the current research control start.
They are not index membership and are not forced to 500 securities.

| Year | Active ordinary | Fully seasoned observed history | 300-session ready | LIQUID_V1 | Top-500 | Top-750 | Top-1000 | Required scope | 252-signal ready | 273-signal ready |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2004 | 852 | 0 | 0 | 0 | 623 | 852 | 852 | 852 | 434 | 0 |
| 2005 | 933 | 774 | 690 | 480 | 681 | 932 | 933 | 932 | 760 | 730 |
| 2006 | 1071 | 844 | 805 | 454 | 680 | 958 | 1071 | 958 | 840 | 819 |
| 2007 | 1231 | 952 | 910 | 507 | 698 | 978 | 1213 | 979 | 961 | 933 |
| 2008 | 1326 | 1155 | 1113 | 542 | 667 | 935 | 1234 | 935 | 1158 | 1132 |
| 2009 | 1350 | 1261 | 1222 | 579 | 629 | 944 | 1266 | 944 | 1244 | 1238 |
| 2010 | 1499 | 1292 | 1262 | 745 | 691 | 949 | 1235 | 962 | 1291 | 1276 |
| 2011 | 3007 | 1296 | 1268 | 554 | 1150 | 1690 | 2191 | 1693 | 1305 | 1285 |
| 2012 | 1592 | 1456 | 1283 | 512 | 635 | 910 | 1175 | 911 | 1398 | 1352 |

`Fully seasoned observed history` uses observed sessions only. Left-censored securities can have older true listing age but still lack pre-source price history.
`Required scope` is `LIQUID_V1_OR_HISTORICAL_TOP750`; low-liquidity names outside that scope do not block early promotion.
