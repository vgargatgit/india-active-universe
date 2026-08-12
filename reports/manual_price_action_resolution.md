# Manual price-action resolution

This report records reviewed corporate-action resolutions used by the deterministic pipeline.
Reviewed genuine market moves remain visible; they are not converted to ordinary `PASS` rows.

| Symbol | Event | Date | Type | Subject | Resolution | Classification | Confidence | Price factor | Share factor | Pre close | Post open | Post close | Residual adjusted return | Holder value ratio | Boundary status | Factor quality | Evidence | Blocking after review? |
|---|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|
| `EXIDEIND` | `NSE_CA_000702` | 2006-09-08 | `SPLIT` | Fv Split Rs.10/- To Re.1/ | `VERIFIED_FACTOR_GENUINE_MARKET_MOVE` | `VERIFIED_FACTOR_GENUINE_MARKET_MOVE` | `MEDIUM_HIGH` | 0.1 | 10.0 | 385.3 | 40.0 | 45.2 | 0.038152089281079604 | 1.0381520892810798 | `PASS` | `OFFICIAL_SPLIT_FACTOR_VERIFIED` | PHASE3_FORENSIC_RESEARCH_NOTE_2026-08-12_EXIDEIND_SPLIT_10_TO_1_VERIFIED | `NO` |
| `LAKSHVILAS` | `NSE_CA_001069` | 2006-11-17 | `BONUS_RIGHTS_COMPOSITE` | Bonus 1:2/Rights 1:1 | `COMPOSITE_BONUS_RIGHTS` | `RESOLVED_COMPOSITE_ACTION` | `HIGH` | 0.5222493888 | 2.5 | 163.6 | 75.2 | 83.95 | -0.11985018734503217 | 0.8435207823960881 | `PASS` | `OFFICIAL_TERMS_COMPOSITE_RESOLVED` | PHASE3_FORENSIC_RESEARCH_NOTE_2026-08-12_LAKSHVILAS_BONUS_1_FOR_2_RIGHTS_1_FOR_1_RS50 | `NO` |
| `JINDALSTEL` | `NSE_CA_002743` | 2008-01-21 | `SPLIT` | Fv Split Rs.5/- To Re.1/- | `VERIFIED_FACTOR_GENUINE_MARKET_MOVE` | `VERIFIED_FACTOR_GENUINE_MARKET_MOVE` | `VERY_HIGH` | 0.2 | 5.0 | 14363.85 | 2961.0 | 2104.25 | 0.03071251788343643 | 1.0307125178834364 | `PASS` | `OFFICIAL_SPLIT_FACTOR_VERIFIED` | PHASE3_FORENSIC_RESEARCH_NOTE_2026-08-12_JINDALSTEL_SPLIT_DURING_2008_MARKET_CRASH | `NO` |
| `SHREEASHTA` | `NSE_CA_005857` | 2010-02-01 | `BONUS` | Bonus 4:1 | `VERIFIED_FACTOR_GENUINE_MARKET_MOVE` | `VERIFIED_FACTOR_GENUINE_MARKET_MOVE` | `HIGH` | 0.2 | 5.0 | 81.0 | 16.3 | 19.45 | 0.006172839506172867 | 1.0061728395061726 | `PASS` | `OFFICIAL_BONUS_FACTOR_VERIFIED` | PHASE3_FORENSIC_RESEARCH_NOTE_2026-08-12_SHREEASHTA_BONUS_4_FOR_1_VERIFIED | `NO` |
| `FCSSOFT` | `NSE_CA_005923` | 2010-02-26 | `BONUS` | Bonus 1:1 | `VERIFIED_FACTOR_GENUINE_MARKET_MOVE` | `VERIFIED_FACTOR_GENUINE_MARKET_MOVE` | `HIGH` | 0.5 | 2.0 | 12.15 | 6.9 | 7.35 | 0.1358024691358024 | 1.1358024691358024 | `PASS` | `OFFICIAL_BONUS_FACTOR_VERIFIED` | PHASE3_FORENSIC_RESEARCH_NOTE_2026-08-12_FCSSOFT_BONUS_1_FOR_1_VERIFIED | `NO` |
| `KWALITY` | `NSE_CA_006139` | 2010-06-15 | `SELECTIVE_BONUS` | Bonus 5:7 | `SELECTIVE_BONUS` | `RESOLVED_SELECTIVE_BONUS` | `HIGH` | 0.8957290918 | 1.116408978 | 163.0 | 138.7 | 138.7 | -0.05002499841908914 | 0.9499750015251531 | `PASS` | `OFFICIAL_CAPITAL_CHANGE_RESOLVED` | PHASE3_FORENSIC_RESEARCH_NOTE_2026-08-12_KWALITY_SELECTIVE_NON_PROMOTER_BONUS_CAPITAL_CHANGE | `NO` |
| `BIRLAPOWER` | `NSE_CA_007424` | 2010-10-20 | `BONUS` | Bonus 1:5 | `VERIFIED_FACTOR_GENUINE_MARKET_MOVE` | `VERIFIED_FACTOR_GENUINE_MARKET_MOVE` | `MEDIUM` | 0.8333333333333334 | 1.2 | 1.85 | 1.7 | 1.85 | 0.10270270270270254 | 1.1027027027027028 | `PASS` | `OFFICIAL_BONUS_FACTOR_VERIFIED` | PHASE3_FORENSIC_RESEARCH_NOTE_2026-08-12_BIRLAPOWER_BONUS_1_FOR_5_VERIFIED | `NO` |
| `NELCAST` | `NSE_CA_008635` | 2011-09-06 | `SPLIT` | Face Value Split From Rs 10 To Rs 2 | `VERIFIED_FACTOR_GENUINE_MARKET_MOVE` | `VERIFIED_FACTOR_GENUINE_MARKET_MOVE` | `MEDIUM_HIGH` | 0.2 | 5.0 | 108.0 | 21.1 | 25.3 | -0.02314814814814814 | 0.9768518518518517 | `PASS` | `OFFICIAL_SPLIT_FACTOR_VERIFIED` | PHASE3_FORENSIC_RESEARCH_NOTE_2026-08-12_NELCAST_SPLIT_10_TO_2_VERIFIED | `NO` |

## Rationale

- `NSE_CA_000702` `EXIDEIND`: Official split factor is correct. The residual boundary return is a genuine market move and must not alter the price-return factor.

- `NSE_CA_001069` `LAKSHVILAS`: Reviewed terms show one bonus share for every two old shares plus one rights share for every one old share at Rs 50. Rights entitlement applies to old shares and excludes bonus shares. Price-return adjustment uses the cash-aware theoretical ex-price formula.

- `NSE_CA_002743` `JINDALSTEL`: Official split factor is correct. The residual boundary return occurred during the January 2008 market crash and is treated as a genuine market move, not an adjustment defect.

- `NSE_CA_005857` `SHREEASHTA`: Official 4:1 bonus factor is correct. The residual boundary return is a genuine market move and must not alter the price-return factor.

- `NSE_CA_005923` `FCSSOFT`: Official 1:1 bonus factor is correct. Vendor representation as a 2-for-1 split does not invalidate the factor. The residual boundary return is a genuine market move.

- `NSE_CA_006139` `KWALITY`: Reviewed capital-change evidence shows the 5:7 bonus was issued only to non-promoter shareholders. Market price-return adjustment therefore uses aggregate dilution from total shares before and after the event, not the public-holder entitlement ratio.

- `NSE_CA_007424` `BIRLAPOWER`: Official 1:5 bonus factor is correct. No reviewed evidence indicates a concurrent adjustment. The residual boundary return is a genuine market move.

- `NSE_CA_008635` `NELCAST`: Official split factor is correct. The residual boundary return is a genuine market move and must not alter the price-return factor.
