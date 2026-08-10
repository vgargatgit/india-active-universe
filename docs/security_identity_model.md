# Security identity model

Ticker is an attribute, not identity. `issuer_id` represents an issuer where continuity is evidenced; `security_id` represents a specific equity security; `listing_episode_id` represents one continuous exchange listing/trading episode. Symbol, ISIN, company name, and series are effective-dated attributes.

Identity quality is explicit: `OFFICIAL_EXCHANGE_IDENTITY`, `MULTI_SOURCE_VERIFIED`, `RECONSTRUCTED_HIGH_CONFIDENCE`, `SINGLE_OFFICIAL_SOURCE`, `PARTIAL`, `UNRESOLVED`, or `MODEL_CANDIDATE_ONLY`. Fuzzy matching can only create review candidates. Symbol reuse and ambiguous date-free lookups are errors.
