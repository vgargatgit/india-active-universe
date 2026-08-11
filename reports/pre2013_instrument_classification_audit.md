# Pre-2013 instrument classification audit

This audit is scoped to securities that enter `LIQUID_V1` or historical Top-750 before the current research control start.
The ordinary-equity gate fails closed for known non-common-equity instruments and ambiguous required-scope classifications.

## Candidate instrument gate

| Candidate start | Required securities | Non-ordinary securities | Ambiguous quality | Known product symbols | Product-like false-positive review | Gate |
|---|---:|---:|---:|---:|---:|---|
| 2011-01-01 | 1004 | 0 | 0 | 0 | 1 | `PASS` |
| 2009-01-01 | 1249 | 0 | 0 | 0 | 4 | `PASS` |
| 2007-01-01 | 1442 | 0 | 0 | 0 | 6 | `PASS` |
| 2006-01-01 | 1597 | 0 | 0 | 0 | 6 | `PASS` |

## Review queue

| Security | Symbol | Company | First month | Last month | Instrument type | Instrument quality | Best rank | Research months | Product-like marker | Known product symbol | Review flag |
|---|---|---|---|---|---|---|---:|---:|---|---|---|
| `SEC_382b0155e115c62a` | `GOLDTECH` | `None` | 2006-06-30 | 2010-06-30 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 250 | 37 | `True` | `False` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_41f32740cfb6b5e2` | `GOLDENTOBC` | `None` | 2008-09-30 | 2010-03-31 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 251 | 14 | `True` | `False` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_7bdd5492bdf39963` | `GOLDIAM` | `None` | 2006-01-31 | 2007-11-30 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 341 | 20 | `True` | `False` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_2ddbe51344594f0b` | `GOLDINFRA` | `None` | 2008-02-29 | 2009-07-31 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 450 | 11 | `True` | `False` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_596633f88da3378f` | `PNBGILTS` | `None` | 2006-01-31 | 2012-12-31 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 463 | 57 | `True` | `False` | `PRODUCT_LIKE_NAME_REVIEW` |
| `SEC_d0694b06e9b5cdff` | `GOLDTELE` | `None` | 2006-01-31 | 2008-01-31 | `ORDINARY_EQUITY` | `HEURISTIC_HIGH_CONFIDENCE` | 616 | 17 | `True` | `False` | `PRODUCT_LIKE_NAME_REVIEW` |

Product-like markers are a review signal only. They do not override source-backed instrument classification by themselves.
Known product symbols are exact-symbol ETF/product blockers and require a source rebuild so they leave the ordinary-equity release artifacts.
Promotion requires zero known non-ordinary and zero ambiguous classifications inside the promoted required scope.
