# Pre-2013 instrument classification audit

This audit is scoped to securities that enter `LIQUID_V1` or historical Top-750 before the current research control start.
The ordinary-equity gate fails closed for known non-common-equity instruments and ambiguous required-scope classifications.

## Candidate instrument gate

| Candidate start | Required securities | Non-ordinary securities | Ambiguous quality | Product-like ordinary names | Gate |
|---|---:|---:|---:|---:|---|
| 2011-01-01 | 1819 | 0 | 0 | 14 | `REVIEW_REQUIRED` |
| 2009-01-01 | 2142 | 0 | 0 | 18 | `REVIEW_REQUIRED` |
| 2007-01-01 | 2349 | 0 | 0 | 20 | `REVIEW_REQUIRED` |
| 2006-01-01 | 2510 | 0 | 0 | 20 | `REVIEW_REQUIRED` |

## Review queue

| Security | Symbol | Company | First month | Last month | Instrument type | Instrument quality | Best rank | Research months | Product-like marker | Review flag |
|---|---|---|---|---|---|---|---:|---:|---|---|
| `SEC_f30fb230beabc7e3` | `KOTAKGOLD` | `None` | 2011-06-30 | 2012-12-31 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 174 | 19 | `True` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_69887a4ff57841de` | `PNBGILTS` | `None` | 2004-01-30 | 2011-05-31 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 228 | 70 | `True` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_83df60533a6d1f7c` | `GOLDTECH` | `None` | 2004-01-30 | 2010-06-30 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 250 | 57 | `True` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_de451e57d4c2984a` | `GOLDENTOBC` | `None` | 2008-09-30 | 2010-03-31 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 251 | 14 | `True` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_04d6751683afe66f` | `GOLDSHARE` | `None` | 2011-06-30 | 2012-12-31 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 253 | 19 | `True` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_2f5d12c134043087` | `RELGOLD` | `None` | 2011-06-30 | 2012-12-31 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 258 | 19 | `True` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_3ab8064e17a9dba9` | `RELGOLD` | `None` | 2007-11-30 | 2011-05-31 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 263 | 43 | `True` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_68d8dc87834c6f93` | `GOLDSHARE` | `None` | 2007-04-30 | 2011-05-31 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 267 | 50 | `True` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_0fc95dfbee6998dd` | `KOTAKGOLD` | `None` | 2007-10-31 | 2011-05-31 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 325 | 42 | `True` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_40385c2f90935646` | `GOLDIAM` | `None` | 2005-08-31 | 2007-11-30 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 341 | 25 | `True` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_3d4f7227e8c4c789` | `IIFLNIFTY` | `None` | 2011-10-31 | 2012-12-31 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 361 | 15 | `True` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_746cf1396ee5aabb` | `GOLDINFRA` | `None` | 2008-02-29 | 2009-07-31 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 450 | 11 | `True` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_d0694b06e9b5cdff` | `GOLDTELE` | `None` | 2004-01-30 | 2008-01-31 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 529 | 32 | `True` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_596633f88da3378f` | `PNBGILTS` | `None` | 2012-03-30 | 2012-12-31 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 591 | 10 | `True` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_2ddbe51344594f0b` | `GOLDINFRA` | `None` | 2011-06-30 | 2011-06-30 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 593 | 1 | `True` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_ed3ac458a14d22b9` | `QGOLDHALF` | `None` | 2008-02-29 | 2009-07-31 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 608 | 10 | `True` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_ee6b9775082944a8` | `AXISGOLD` | `None` | 2011-09-30 | 2012-12-31 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 631 | 16 | `True` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_fcb4de16e1dd7abe` | `AGEEGOLD` | `None` | 2004-01-30 | 2005-02-28 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 637 | 13 | `True` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_61b33d7674b3b4d5` | `IDBIGOLD` | `None` | 2011-11-30 | 2012-11-30 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 639 | 9 | `True` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_5ace4461bc3b5352` | `QGOLDHALF` | `None` | 2011-08-30 | 2012-12-31 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 647 | 17 | `True` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_0c218cfeafa428d6` | `MGOLD` | `None` | 2012-03-30 | 2012-12-31 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 661 | 10 | `True` | `PRODUCT_LIKE_NAME_REVIEW` |

Product-like markers are a review signal only. They do not override source-backed instrument classification by themselves.
Promotion requires zero known non-ordinary and zero ambiguous classifications inside the promoted required scope.
