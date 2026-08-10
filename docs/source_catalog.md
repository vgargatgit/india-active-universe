# Source catalog

## Primary

- NSE historical bhavcopies and security-wise archives: dated market observations.
- NSE security masters, listing/delisting notices, circulars, and corporate-action records: identity and event evidence.
- NSE press-release archive: dated suspension and suspension-revocation evidence. Company-name matches from this source remain review records until an effective-dated identity is confirmed.

## Secondary official

- BSE security master, notices, and historical information for corroboration.
- SEBI/regulatory material for documented corporate or terminal events.

## QA only

Yahoo Finance and other public providers may compare overlapping observations but never define the historical universe or canonical prices.

Each retrieval is cached without overwrite and recorded in a manifest with URL, retrieval time, source date, SHA256, HTTP metadata, parser version, and status. HTML/error payloads fail integrity validation.

The initial bulk loader uses the official legacy NSE equity archive pattern for historical dates (`cmDDMONYYYYbhav.csv.zip`) and the official CM UDiFF pattern for newer dates. Each response is downloaded to a temporary file, checked as a ZIP with required market columns, and moved into RAW only after validation. Existing invalid files are never overwritten. Missing exchange holidays remain missing rather than becoming synthetic sessions.
