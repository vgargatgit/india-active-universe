# Known limitations

The MVP does not claim complete historical corporate-action, dividend, delisting, suspension, market-cap, or sector coverage. Unresolved identities and terminal values remain explicit. Current-only sector labels must be marked `CURRENT_BACKCAST`; missing historical market cap must not be fabricated. Research confidence is date-range-specific.

The v2.0 release has complete official daily observation coverage for its downloaded date range. Corporate actions and selected official delisting evidence are populated, but suspension, merger, insolvency, and terminal-value classification is not complete. Its corporate-action boundary audit contains warnings and missing prices; warnings do not remove raw observations. Unknown status intervals must not be interpreted as suspensions. Its adjusted-price artifact uses `NO_ADJUSTMENT_REQUIRED` for rows with no applicable price action, `PRICE_ACTION_ADJUSTED_VERIFIED` for rows adjusted by verified price-action factors, and `TOTAL_RETURN_PARTIAL` for the separate dividend-aware series.

Scanned delisting notices remain in the immutable raw layer and inventory. OCR is an optional evidence-enrichment step and requires external `pdftoppm` and `tesseract` tools; without them the workflow fails explicitly with `OCR_UNAVAILABLE` and does not create canonical identities.

The manual identity override file is empty in the current release. Non-empty overrides require the optional PyYAML dependency and pass the evidence-backed validator before use.
