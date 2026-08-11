# Extended history research readiness

This report answers whether the bounded liquid decision universe can move before the current 2013 control start.
It is generated from release artifacts and companion audit reports. It does not promote an interval by prose.

## Executive answers

1. Earliest official source date: `2004-01-01`.
2. Reliable pre-2006 history found: `YES` based on `4` valid representative probes out of `4`.
3. Earliest 60-session readiness: `2004-03-30`.
4. Earliest 126-session readiness: `2004-07-05`.
5. Earliest 252-session readiness: `2005-01-03`.
6. Earliest 272-session eligibility readiness: `2005-02-02`.
7. Earliest 273-session momentum-style readiness: `2005-02-03`.
8. Earliest fully warmed research date: `2005-03-14`.
9. Years passing identity promotion: see `pre2013_research_identity_promotion.md` and `research_readiness_by_year.md`.
10. Years failing promotion: see `research_readiness_by_year.md`.
11. Early identities requiring intervention: see `pre2013_identity_priority.md` and `pre2013_identity_episode_audit.md`.
12. Required securities unresolved before `2013-01-01`: `0` monthly required-scope identity failures.
13. Material corporate actions lacking factors in promoted required scope: `0`.
14. Left-censored material boundaries: `341`.
15. Boundary contamination capability: see `pre2013_adjusted_return_quality.md`; only candidate lookback/signal-window non-PASS boundaries are promotion-relevant.
16. Price-return series trust: `price_return_adjusted_close` is the promoted signal series when price-action candidate gates pass.
17. Liquidity features session-correct: `session_correct_liquidity_audit.md` documents official-session windows.
18. Survivorship protection: see `pre2013_survivorship_evidence.md` and `survivorship_audit.md`.
19. 2013+ v2.0.1 regression status: `REVIEW_REQUIRED`.
20. RESEARCH_HIGH_CONFIDENCE intervals:
- `2013-01-01` through `2026-08-10`: `RESEARCH_HIGH_CONFIDENCE` for `NSE_BROAD_LIQUID_PIT_V1` / `LIQUID_V1`
- `2004-01-01` through `2005-03-14`: `SOURCE_ONLY` for `NSE_BROAD_LIQUID_PIT_V1` / `LIQUID_V1`
21. RESEARCH_EXPLORATORY intervals: any interval marked `RESEARCH_EXPLORATORY` in `research_quality_intervals`, plus candidate intervals whose gates are not all pass.
22. SOURCE_ONLY interval: source observations before the first promoted research interval remain `SOURCE_ONLY` or warmup-only evidence.
23. Downstream Model Arena safe pre-2013 start: not declared by this report unless all hard gates plus CI/test evidence pass.
24. Earliest candidate gate-pass start: `None`. Refined earliest monthly/session boundary: `None`. Candidate recommended PIT-universe interval: `{'status': 'NO_REFINED_BOUNDARY', 'start': None, 'end': '2026-08-10', 'profile': 'NSE_BROAD_LIQUID_PIT_V1', 'profile_version': 'LIQUID_V1', 'boundary_scan_method': 'MONTHLY_SNAPSHOT_BOUNDARIES_WITH_OFFICIAL_SESSION_LOOKBACK', 'promotion_status': 'NOT_PROMOTED_UNLESS_PRESENT_IN_RESEARCH_QUALITY_INTERVALS', 'interval_type': 'PIT_UNIVERSE', 'feature_readiness_policy': 'FEATURE_READINESS_REPORTED_SEPARATELY'}`. This is not a final safe start unless full release evidence also passes.
25. Remaining limitations: terminal values and total-return dividends remain partial; market cap and historical sector data are not fabricated.

## Candidate gate matrix

A missing candidate audit row is an explicit non-pass state.
| Candidate start | Candidate audit | Decision-window gate | Warmup gate | Session-liquidity gate | Identity gate | Price-action gate | Instrument gate | Status gate | Hard failures | Promotion interpretation |
|---|---|---|---|---|---|---|---|---|---|---|
| 2011-01-01 | `FAIL` | `PASS` | `FAIL` | `PASS` | `PASS` | `REVIEW_REQUIRED` | `REVIEW_REQUIRED` | `PASS` | `signal_window_non_pass_boundaries=76` | `NOT_READY` |
| 2009-01-01 | `FAIL` | `PASS` | `FAIL` | `PASS` | `PASS` | `REVIEW_REQUIRED` | `REVIEW_REQUIRED` | `PASS` | `signal_window_non_pass_boundaries=153` | `NOT_READY` |
| 2007-01-01 | `FAIL` | `PASS` | `FAIL` | `PASS` | `PASS` | `REVIEW_REQUIRED` | `REVIEW_REQUIRED` | `PASS` | `signal_window_non_pass_boundaries=238` | `NOT_READY` |
| 2006-01-01 | `FAIL` | `PASS` | `FAIL` | `PASS` | `PASS` | `REVIEW_REQUIRED` | `REVIEW_REQUIRED` | `PASS` | `signal_window_non_pass_boundaries=238` | `NOT_READY` |

## Final promotion rule

PIT universe interval: `SOURCE_INTEGRITY = PASS`, `SESSION_LIQUIDITY = PASS`, `RESEARCH_IDENTITY_FAILURES = 0`, `MATERIAL_PRICE_ACTION_MISSING_FACTORS = 0`, `INSTRUMENT_SCOPE_FAILURES = 0`, `PIT_INVARIANTS = PASS`, and `CI = PASS`.

Feature/model-ready research interval: the PIT universe interval gates must pass, and `WARMUP_READINESS = PASS` for the required published feature/model windows. Do not remove otherwise valid universe securities only because a downstream model feature is not ready.

Terminal values and complete total-return history are not required for price-return alpha research, but their limitations must remain explicit.
