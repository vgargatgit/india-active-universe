# Known limitations

The MVP does not claim complete historical corporate-action, dividend, delisting, suspension, market-cap, or sector coverage. Unresolved identities and terminal values remain explicit. Current-only sector labels must be marked `CURRENT_BACKCAST`; missing historical market cap must not be fabricated. Research confidence is date-range-specific.

The current materialized release has complete official daily observation coverage for its downloaded date range. Corporate actions and selected official delisting evidence are populated, but suspension, merger, insolvency, and terminal-value classification is not complete. Unknown status intervals must not be interpreted as suspensions. Its adjusted-price artifact applies verified bonus factors and labels the remainder `RAW_ONLY`; it is not a complete split/bonus/dividend or total-return series.
