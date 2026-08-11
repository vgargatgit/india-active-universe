# Research readiness by year

This matrix is diagnostic. A `PASS` year still requires source integrity, PIT invariant, test, CI, and regression evidence before promotion.
The readiness score is diagnostic only. Hard gates remain authoritative.

| Year | Official sessions | Fully warmed sessions | Active ordinary | LIQUID_V1 | Top-750 | Required securities | Identity failures | Instrument failures | Missing material factors | Boundary warnings | Unknown-status exclusions | Terminal sensitivity count | Research invariant failures | Readiness score | Promotion status |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2004 | 252 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 4/5 | `FAIL` |
| 2005 | 249 | 201 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5/5 | `PASS` |
| 2006 | 247 | 247 | 1071 | 454 | 958 | 958 | 0 | 0 | 1 | 3 | 0 | 456 | 0 | 4/5 | `FAIL` |
| 2007 | 249 | 249 | 1228 | 507 | 975 | 976 | 0 | 0 | 0 | 2 | 0 | 418 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2008 | 246 | 246 | 1322 | 540 | 934 | 934 | 0 | 0 | 0 | 4 | 0 | 402 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2009 | 242 | 242 | 1346 | 576 | 943 | 943 | 0 | 0 | 0 | 3 | 0 | 379 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2010 | 251 | 251 | 1494 | 742 | 952 | 964 | 0 | 0 | 0 | 5 | 0 | 363 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2011 | 247 | 247 | 1589 | 598 | 911 | 911 | 0 | 0 | 0 | 1 | 0 | 324 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2012 | 247 | 247 | 1564 | 569 | 899 | 899 | 0 | 0 | 0 | 0 | 0 | 298 | 0 | 5/5 | `PASS` |
| 2013 | 248 | 248 | 1547 | 525 | 881 | 881 | 0 | 0 | 0 | 1 | 0 | 283 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2014 | 243 | 243 | 1524 | 750 | 904 | 914 | 0 | 0 | 0 | 5 | 0 | 246 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2015 | 247 | 247 | 1525 | 834 | 905 | 929 | 0 | 0 | 0 | 4 | 0 | 234 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2016 | 246 | 246 | 1583 | 904 | 935 | 1013 | 0 | 0 | 0 | 0 | 0 | 238 | 0 | 5/5 | `PASS` |
| 2017 | 248 | 248 | 1626 | 1012 | 927 | 1097 | 0 | 0 | 0 | 3 | 0 | 227 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2018 | 246 | 246 | 1615 | 1037 | 889 | 1103 | 0 | 0 | 0 | 4 | 0 | 197 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2019 | 244 | 244 | 1634 | 768 | 883 | 886 | 0 | 0 | 0 | 0 | 0 | 129 | 0 | 5/5 | `PASS` |
| 2020 | 250 | 250 | 1658 | 871 | 899 | 969 | 0 | 0 | 0 | 2 | 0 | 120 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2021 | 248 | 248 | 1779 | 1169 | 930 | 1274 | 0 | 0 | 0 | 11 | 0 | 157 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2022 | 248 | 248 | 1889 | 1278 | 923 | 1372 | 0 | 0 | 0 | 12 | 0 | 155 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2023 | 245 | 245 | 1969 | 1348 | 971 | 1450 | 0 | 0 | 0 | 6 | 0 | 146 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2024 | 246 | 246 | 2031 | 1524 | 974 | 1649 | 0 | 0 | 0 | 16 | 0 | 171 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2025 | 248 | 248 | 2198 | 1485 | 992 | 1636 | 0 | 0 | 0 | 12 | 0 | 126 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2026 | 148 | 148 | 2361 | 1450 | 883 | 1572 | 0 | 0 | 0 | 1 | 0 | 86 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |

Readiness score dimensions: source sessions present, full warmup present, identity gate clean, price-action gate clean, and instrument gate clean.
A year cannot receive `PASS` unless at least one monthly decision session is fully warmed for the longest configured feature window.
Boundary warnings are not automatically fatal when they are left-boundary limitations that cannot contaminate a promoted signal window.
Promotion remains date-range scoped; this report does not force 2006-2026 to pass atomically.
