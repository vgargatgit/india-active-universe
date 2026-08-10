# Security identity model

Ticker is an attribute, not identity. `issuer_id` represents an issuer where continuity is evidenced; `security_id` represents a specific equity security; `listing_episode_id` represents one continuous exchange listing/trading episode. Symbol, ISIN, company name, and series are effective-dated attributes.

Identity quality is explicit: `OFFICIAL_EXCHANGE_IDENTITY`, `MULTI_SOURCE_VERIFIED`, `RECONSTRUCTED_HIGH_CONFIDENCE`, `SINGLE_OFFICIAL_SOURCE`, `PARTIAL`, `UNRESOLVED`, or `MODEL_CANDIDATE_ONLY`. Fuzzy matching can only create review candidates. Symbol reuse and ambiguous date-free lookups are errors.

Manual identity overrides are stored in `data/reference/manual_identity_overrides.yaml`. An override must be date-bounded, target NSE `EQ`, cite at least one evidence reference, include a rationale, and have `review_status: APPROVED`. Overlapping ranges are rejected. An unresolved or fuzzy candidate cannot become canonical through this file.
