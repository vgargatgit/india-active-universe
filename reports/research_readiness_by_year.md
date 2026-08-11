# Research readiness by year

This matrix is diagnostic. A `PASS` year still requires source integrity, PIT invariant, test, CI, and regression evidence before promotion.
The readiness score is diagnostic only. Hard gates remain authoritative.

| Year | Official sessions | Fully warmed sessions | Active ordinary | LIQUID_V1 | Top-750 | Required securities | Identity failures | Instrument failures | Missing material factors | Boundary warnings | Unknown-status exclusions | Terminal sensitivity count | Research invariant failures | Readiness score | Promotion status |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2004 | 252 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 4/5 | `FAIL` |
| 2005 | 249 | 201 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5/5 | `PASS` |
| 2006 | 247 | 247 | 1071 | 454 | 958 | 958 | 0 | 0 | 0 | 0 | 0 | 233 | 0 | 5/5 | `PASS` |
| 2007 | 249 | 249 | 1228 | 507 | 975 | 976 | 0 | 0 | 0 | 0 | 0 | 178 | 0 | 5/5 | `PASS` |
| 2008 | 246 | 246 | 1322 | 540 | 934 | 934 | 0 | 0 | 0 | 0 | 0 | 143 | 0 | 5/5 | `PASS` |
| 2009 | 242 | 242 | 1346 | 576 | 943 | 943 | 0 | 0 | 0 | 0 | 0 | 108 | 0 | 5/5 | `PASS` |
| 2010 | 251 | 251 | 1494 | 742 | 952 | 964 | 0 | 0 | 0 | 0 | 0 | 74 | 0 | 5/5 | `PASS` |
| 2011 | 247 | 247 | 2995 | 551 | 1691 | 1694 | 0 | 0 | 0 | 10 | 0 | 338 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2012 | 247 | 247 | 1584 | 509 | 916 | 916 | 0 | 0 | 0 | 4 | 0 | 300 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2013 | 248 | 248 | 1560 | 517 | 890 | 890 | 0 | 0 | 0 | 1 | 0 | 284 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2014 | 243 | 243 | 1549 | 745 | 918 | 929 | 0 | 0 | 0 | 6 | 0 | 244 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2015 | 247 | 247 | 1552 | 819 | 926 | 949 | 0 | 0 | 0 | 8 | 0 | 231 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2016 | 246 | 246 | 1616 | 892 | 957 | 1035 | 0 | 0 | 0 | 4 | 0 | 236 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2017 | 248 | 248 | 1654 | 1000 | 945 | 1112 | 0 | 0 | 0 | 5 | 0 | 223 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2018 | 246 | 246 | 1637 | 1029 | 903 | 1114 | 0 | 0 | 0 | 5 | 0 | 194 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2019 | 244 | 244 | 1641 | 764 | 888 | 891 | 0 | 0 | 0 | 1 | 0 | 127 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2020 | 250 | 250 | 1668 | 870 | 906 | 976 | 0 | 0 | 0 | 2 | 0 | 116 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2021 | 248 | 248 | 1803 | 1166 | 947 | 1290 | 0 | 0 | 0 | 10 | 0 | 153 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2022 | 248 | 248 | 1932 | 1267 | 947 | 1391 | 0 | 0 | 0 | 14 | 0 | 149 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2023 | 245 | 245 | 2000 | 1341 | 982 | 1458 | 0 | 0 | 0 | 35 | 0 | 136 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2024 | 246 | 246 | 2074 | 1519 | 994 | 1669 | 0 | 0 | 0 | 47 | 0 | 161 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2025 | 248 | 248 | 2233 | 1468 | 1008 | 1643 | 0 | 0 | 0 | 31 | 0 | 105 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2026 | 148 | 148 | 2377 | 1428 | 888 | 1573 | 0 | 0 | 0 | 12 | 0 | 66 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |

Readiness score dimensions: source sessions present, full warmup present, identity gate clean, price-action gate clean, and instrument gate clean.
A year cannot receive `PASS` unless at least one monthly decision session is fully warmed for the longest configured feature window.
Boundary warnings are not automatically fatal when they are left-boundary limitations that cannot contaminate a promoted signal window.
Promotion remains date-range scoped; this report does not force 2006-2026 to pass atomically.
