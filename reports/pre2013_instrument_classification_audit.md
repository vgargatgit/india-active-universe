# Pre-2013 instrument classification audit

This audit is scoped to securities that enter `LIQUID_V1` or historical Top-750 before the current research control start.
The ordinary-equity gate fails closed for known non-common-equity instruments and ambiguous required-scope classifications.

## Candidate instrument gate

| Candidate start | Required securities | Non-ordinary securities | Ambiguous quality | Known product symbols | Product-like false-positive review | Gate |
|---|---:|---:|---:|---:|---:|---|
| 2011-01-01 | 1818 | 0 | 0 | 0 | 3 | `PASS` |
| 2009-01-01 | 2138 | 0 | 0 | 0 | 6 | `PASS` |
| 2007-01-01 | 2345 | 0 | 0 | 0 | 8 | `PASS` |
| 2006-01-01 | 2505 | 0 | 0 | 0 | 8 | `PASS` |

## Review queue

| Security | Symbol | Company | First month | Last month | Instrument type | Instrument quality | Best rank | Research months | Product-like marker | Known product symbol | Review flag |
|---|---|---|---|---|---|---|---:|---:|---|---|---|
| `SEC_83df60533a6d1f7c` | `GOLDTECH` | `None` | 2006-06-30 | 2010-06-30 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 250 | 37 | `True` | `False` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_de451e57d4c2984a` | `GOLDENTOBC` | `None` | 2008-09-30 | 2010-03-31 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 251 | 14 | `True` | `False` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_40385c2f90935646` | `GOLDIAM` | `None` | 2006-01-31 | 2007-11-30 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 341 | 20 | `True` | `False` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_746cf1396ee5aabb` | `GOLDINFRA` | `None` | 2008-02-29 | 2009-07-31 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 450 | 11 | `True` | `False` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_69887a4ff57841de` | `PNBGILTS` | `None` | 2006-01-31 | 2011-05-31 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 463 | 47 | `True` | `False` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_596633f88da3378f` | `PNBGILTS` | `None` | 2012-03-30 | 2012-12-31 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 591 | 10 | `True` | `False` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_2ddbe51344594f0b` | `GOLDINFRA` | `None` | 2011-06-30 | 2011-06-30 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 593 | 1 | `True` | `False` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_d0694b06e9b5cdff` | `GOLDTELE` | `None` | 2006-01-31 | 2008-01-31 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 616 | 17 | `True` | `False` | `PRODUCT_LIKE_NAME_REVIEW` |

Product-like markers are a review signal only. They do not override source-backed instrument classification by themselves.
Known product symbols are exact-symbol ETF/product blockers and require a source rebuild so they leave the ordinary-equity release artifacts.
Promotion requires zero known non-ordinary and zero ambiguous classifications inside the promoted required scope.
