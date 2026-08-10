# Terminal event audit

Release `india_equity_data_v1.7.0` contains 1,903 terminal-event rows: 95 dated compulsory-delisting notices, 452 official-workbook rows requiring identity review, and 1,356 observation-gap unknowns. Its status intervals link 86 dated compulsory delistings and retain 1,270 post-observation intervals as `UNKNOWN_STATUS`. Active and delisted status intervals do not overlap. The official delisted workbook has no exit-price field. No terminal value is assigned; downstream consumers must treat terminal value as unknown rather than zero until the event and identity are fully linked.

The release also contains 60 NSE notice documents. Twelve have relevant readable delisting text, three need relevance review, nine are unrelated readable documents, and 36 are scanned documents that need OCR. Notice evidence does not change canonical status until identity and event dates are reviewed.

The release also contains 185 historical suspension or revocation evidence rows from 2006-2015. All rows are page-level evidence records and require event-level identity review. One hundred and thirteen are suspension-start candidates and 72 are revocation candidates. One hundred and one rows contain an extracted effective date. These rows do not create canonical suspension intervals.

Event-level parsing identifies 97 explicit action blocks: 26 suspension-start candidates and 71 recommencement or revocation candidates. Ten have an exact company-name and date match. They remain evidence rows because some are recommencements and some securities have later observed trading.
