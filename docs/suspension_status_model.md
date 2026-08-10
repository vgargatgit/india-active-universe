# Suspension status model

The canonical status intervals use official NSE trading observations as the base evidence.

The suspension overlay is conservative:

- A notice is eligible for identity resolution only when one exact normalized company name maps to one NSE ordinary-equity security.
- A `SUSPENSION_START` event is bounded by the first subsequent official trading observation for that security.
- The bounded interval is labelled `SUSPENDED`.
- A notice without a unique identity remains review evidence and does not change canonical status.
- Absence of a daily row alone does not create a suspension interval.

Release v1.8 resolves 18 of 97 parsed event blocks. Two exact suspension starts produce bounded suspended intervals. The remaining events are preserved in `suspension_notice_events.parquet` and `suspension_events_resolved.parquet` for review.

This is evidence enrichment, not a claim that every historical suspension has been recovered.
