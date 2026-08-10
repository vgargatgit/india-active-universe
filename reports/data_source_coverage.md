# Data source coverage

The expected session set is the date set in `trading_calendar.parquet`.
This is an archive integrity audit. It does not claim an independent exchange calendar.

- Manifest entries: `5,084`.
- Valid archive entries: `5,084`.
- Duplicate source dates: `0`.
- Expected official sessions: `5,084`.
- Missing expected source dates: `0`.
- Unexpected source dates: `0`.
- Invalid or failed manifest entries: `0`.

Source integrity gate: `PASS`.

## Missing expected dates

None.

## Unexpected dates

None.

Retrieval timestamps use local file modification time when the original HTTP timestamp is not available.
