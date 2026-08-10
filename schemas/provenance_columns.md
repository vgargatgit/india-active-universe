# Required provenance columns

Canonical and derived rows must retain `source_file_id`, `source_sha256`, `parser_version`, and `canonicalization_version`. Event-derived rows additionally retain `source_event_ids` and `factor_reason` where applicable.
