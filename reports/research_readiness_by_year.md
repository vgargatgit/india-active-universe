# Research readiness by year

This matrix is diagnostic. A `PASS` year still requires source integrity, PIT invariant, test, CI, and regression evidence before promotion.
The readiness score is diagnostic only. Hard gates remain authoritative.

| Year | Official sessions | Fully warmed sessions | Active ordinary | LIQUID_V1 | Top-750 | Required securities | Identity failures | Instrument failures | Missing material factors | Boundary warnings | Unknown-status exclusions | Terminal sensitivity count | Research invariant failures | Readiness score | Promotion status |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2004 | 252 | 0 | 852 | 0 | 852 | 852 | 0 | 0 | 0 | 0 | 0 | 200 | 0 | 4/5 | `FAIL` |
| 2005 | 249 | 201 | 933 | 480 | 932 | 932 | 0 | 0 | 0 | 0 | 0 | 228 | 0 | 5/5 | `PASS` |
| 2006 | 247 | 247 | 1071 | 454 | 958 | 958 | 0 | 0 | 0 | 0 | 0 | 233 | 0 | 5/5 | `PASS` |
| 2007 | 249 | 249 | 1231 | 507 | 978 | 979 | 0 | 0 | 0 | 0 | 0 | 180 | 0 | 5/5 | `PASS` |
| 2008 | 246 | 246 | 1326 | 542 | 935 | 935 | 0 | 0 | 0 | 0 | 0 | 145 | 0 | 5/5 | `PASS` |
| 2009 | 242 | 242 | 1350 | 579 | 944 | 944 | 0 | 0 | 0 | 0 | 0 | 110 | 0 | 5/5 | `PASS` |
| 2010 | 251 | 251 | 1499 | 745 | 949 | 962 | 0 | 0 | 0 | 0 | 0 | 76 | 0 | 5/5 | `PASS` |
| 2011 | 247 | 247 | 3007 | 554 | 1690 | 1693 | 0 | 0 | 0 | 10 | 0 | 341 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2012 | 247 | 247 | 1592 | 512 | 910 | 911 | 0 | 0 | 0 | 4 | 0 | 301 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2013 | 248 | 248 | 1568 | 520 | 893 | 893 | 0 | 0 | 0 | 1 | 0 | 287 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2014 | 243 | 243 | 1557 | 748 | 921 | 932 | 0 | 0 | 0 | 6 | 0 | 247 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2015 | 247 | 247 | 1561 | 821 | 926 | 951 | 0 | 0 | 0 | 8 | 0 | 231 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2016 | 246 | 246 | 1622 | 894 | 959 | 1037 | 0 | 0 | 0 | 4 | 0 | 237 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2017 | 248 | 248 | 1659 | 1000 | 945 | 1112 | 0 | 0 | 0 | 5 | 0 | 223 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2018 | 246 | 246 | 1642 | 1029 | 903 | 1114 | 0 | 0 | 0 | 5 | 0 | 194 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2019 | 244 | 244 | 1646 | 765 | 889 | 892 | 0 | 0 | 0 | 1 | 0 | 127 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2020 | 250 | 250 | 1673 | 873 | 908 | 979 | 0 | 0 | 0 | 2 | 0 | 116 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2021 | 248 | 248 | 1808 | 1168 | 948 | 1292 | 0 | 0 | 0 | 10 | 0 | 153 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2022 | 248 | 248 | 1934 | 1268 | 947 | 1392 | 0 | 0 | 0 | 14 | 0 | 149 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2023 | 245 | 245 | 2002 | 1342 | 982 | 1459 | 0 | 0 | 0 | 35 | 0 | 136 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2024 | 246 | 246 | 2075 | 1520 | 994 | 1670 | 0 | 0 | 0 | 47 | 0 | 161 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2025 | 248 | 248 | 2233 | 1468 | 1008 | 1643 | 0 | 0 | 0 | 31 | 0 | 105 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |
| 2026 | 148 | 148 | 2377 | 1428 | 888 | 1573 | 0 | 0 | 0 | 12 | 0 | 66 | 0 | 5/5 | `PASS_WITH_SCOPED_LIMITATION` |

Readiness score dimensions: source sessions present, full warmup present, identity gate clean, price-action gate clean, and instrument gate clean.
A year cannot receive `PASS` unless at least one monthly decision session is fully warmed for the longest configured feature window.
Boundary warnings are not automatically fatal when they are left-boundary limitations that cannot contaminate a promoted signal window.
Promotion remains date-range scoped; this report does not force 2006-2026 to pass atomically.
