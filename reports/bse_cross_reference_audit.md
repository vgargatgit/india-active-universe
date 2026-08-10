# BSE cross-reference audit

Release `india_equity_data_v1.11.0` contains no BSE security-master, notice, or historical-security source files in `data/raw`. No NSE-to-BSE mapping is therefore promoted to the canonical model.

This is an explicit source boundary. Future BSE evidence must include source hashes, effective dates, and an identity quality label before it can enrich the NSE security master or terminal-event registry.
