# Adjustment methodology

Persist cumulative adjustment factors and their event IDs. Research price adjustment is distinct from total-return adjustment. Release `india_equity_data_v2.0.0` applies unambiguous official bonus ratios and face-value split transitions. `NO_ADJUSTMENT_REQUIRED` means no verified price action applies to the row. `PRICE_ACTION_ADJUSTED_VERIFIED` means verified split, reverse-split, or bonus factors apply. The separate dividend-aware series is labelled `TOTAL_RETURN_PARTIAL`. Compound capital-reduction events, rights, mergers, missing dividend amounts, and missing ex-date closes remain partial. No silently implied total return series is published.

Boundary validation distinguishes `NO_PRE_EVENT_OBSERVATION`, `NO_POST_EVENT_OBSERVATION`, and `NO_BOUNDARY_OBSERVATIONS` from a two-sided holder-value warning. These edge cases are preserved as evidence gaps. They are not converted into a guessed price or return.

Preference-share bonuses are retained as official events but are not applied to the ordinary-equity price series. Multiple same-day ordinary-equity actions are validated with their combined price and share factors.
