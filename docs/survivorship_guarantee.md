# Survivorship guarantee

Historical membership is discovered from historical exchange observations. For any date T, no listing after T can appear, no future symbol mapping is needed to infer membership, and liquidity/history features use data <= T. A security that later disappears remains in earlier active snapshots. This repository does not use current constituents or NIFTY 500 membership.

`scripts/validate_pit.py` exercises future-listing, future-liquidity, symbol rename/reuse, historical dead-security, and future-corporate-action cases.

## Extended-history candidates

Phase 3 may materialize candidate monthly snapshots before the promoted research start. These snapshots do not change the survivorship guarantee and do not create a new trusted research interval by themselves.

For pre-2013 bounded-liquid research, consumers must read:

- `research_quality_intervals` for the promoted trusted range.
- `candidate_promotion_decisions` for configured earlier starts.
- `earliest_candidate_gate_pass_start` as candidate evidence only.
- Candidate hard-failure counts before using any earlier date.

If the candidate evidence is absent or fails any gate, the safe result is not promoted. The data can still be useful for reconnaissance, but it must not be described as research-ready for that earlier start.
