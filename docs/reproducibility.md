# Reproducibility

Each release records release ID, build commit field, config hash, raw-source manifest hash, parser versions, artifact hashes, coverage, quality tier, and quality summary. Bulk source manifests use the local file modification time when the original HTTP retrieval timestamp is not available. This limitation is explicit. Same inputs and configuration must produce the same outputs.

For Phase 2, release `india_equity_data_v2.0.0` must be built from the current source pipeline. Do not use a cached promotion from an older release as a substitute. The source build records the actual Git commit, source manifest hash, manual override hash, config hash, parser versions, artifact hashes, test result hash, CI status hash, and quality report hashes.

Release audit is fail-closed. It writes the report before returning a non-zero status when the manifest does not match the release directory, a required artifact is missing, or a published artifact hash differs from the manifest.

## Phase 3 candidate promotion evidence

Phase 3 extends the evidence path for earlier research starts without silently promoting them. A release manifest must keep the promoted `research_quality_intervals` separate from candidate promotion evidence.

The candidate promotion evidence records:

- `candidate_promotion_decisions`: one decision for each configured candidate start date.
- `earliest_candidate_gate_pass_start`: the manifest-recorded earliest configured candidate start whose candidate gates pass, or `null`.
- `recorded_earliest_candidate_gate_pass_start`: the API summary copy of the manifest-recorded earliest candidate start.
- Derived `earliest_candidate_gate_pass_start`: the API summary value computed from row-level candidate evidence.
- `recorded_matches_derived_earliest_candidate_gate_pass_start`: whether the manifest-recorded earliest candidate start matches the row-derived value.
- `candidate_gate_pass_start_dates`: the full derived chronological list of configured starts whose audit status, first-class gates, and promotion interpretation pass.
- `candidate_research_ready_start_dates`: the derived list of configured starts that also have `RESEARCH_HIGH_CONFIDENCE`.
- `candidate_gate_pass_ready(candidate_start)`: the API helper for checking whether one configured candidate start is in the derived gate-pass set. It rejects unconfigured candidate dates instead of returning `False` for a typo.
- `candidate_research_ready_start_dates()`: the API helper that returns configured starts with both candidate gate-pass evidence and `RESEARCH_HIGH_CONFIDENCE`.
- `candidate_research_ready(candidate_start)`: the API helper that requires both candidate gate-pass evidence and `RESEARCH_HIGH_CONFIDENCE` at the candidate date.
- `candidate_recommended_pit_universe_interval`: the refined candidate interval for PIT-universe release audit. Feature/model readiness is reported separately and must not be used to remove otherwise valid universe securities.
- Candidate audit metadata: profile, profile version, priority scope, control start, required prior sessions, and the configured candidate start dates.
- Gate results for session-liquidity, identity, price-action, instrument, and status checks. Warm-up is reported as advisory feature-readiness evidence. It is not a first-class PIT universe promotion gate.
- `decision_window_gate`, backed by monthly snapshots after the first source-backed candidate decision session.
- Explicit hard-failure counts for each configured gate.

A candidate gate pass is not a release promotion by itself. A downstream consumer must treat the trusted research interval as the interval published in `research_quality_intervals`. Candidate evidence is advisory until the full release audit, source coverage, artifact hashes, and quality reports support promotion.

`CANDIDATE_GATE_PASS_INTERPRETATION` requires every first-class candidate gate to be `PASS`. The ordered gate set is published in the profile constants as `CANDIDATE_DECISION_GATE_KEYS`. The required candidate decision schema is published as `CANDIDATE_DECISION_REQUIRED_FIELDS`.

The candidate promotion summary schema is published as `CANDIDATE_PROMOTION_SUMMARY_FIELDS`.

The candidate promotion API helper names are published as `CANDIDATE_PROMOTION_API_METHODS`.

Allowed candidate audit status values, candidate gate values, and promotion interpretations are published as `CANDIDATE_AUDIT_STATUS_VALUES`, `CANDIDATE_DECISION_GATE_VALUES`, and `CANDIDATE_PROMOTION_INTERPRETATION_VALUES`. Individual promotion interpretation constants include `CANDIDATE_GATE_PASS_INTERPRETATION`, `CANDIDATE_AUDIT_NOT_RECORDED_INTERPRETATION`, `CANDIDATE_NOT_MATERIALIZED_INTERPRETATION`, and `CANDIDATE_NOT_READY_INTERPRETATION`.

Shared primitive candidate values are published as `CANDIDATE_PASS_VALUE`, `CANDIDATE_FAIL_VALUE`, and `CANDIDATE_NOT_RECORDED_VALUE`.

Candidate evidence is all-or-empty at the configured-start level. If `candidate_promotion_decisions` is present and non-empty, it must contain exactly one row for each start in `CANDIDATE_RESEARCH_START_DATES`, including `2006-01-01`. The API normalizes these rows into configured-start order so downstream reproducibility does not depend on manifest row order.

Candidate manifest fields are atomic. In each manifest layer, `candidate_promotion_decisions` and `earliest_candidate_gate_pass_start` must be published together or omitted together. A manifest cannot publish row-level candidate evidence without the release-level earliest-candidate summary, and it cannot publish the summary without the row-level evidence. If row-level decisions include `refined_earliest_passing_snapshot`, the manifest must also publish `refined_earliest_candidate_gate_pass_boundary`.

If candidate evidence is missing, malformed, stale, contradictory, or not generated for every configured candidate start, the release audit fails closed. This prevents an accidental claim that the bounded liquid universe is research-ready from 2006.

Candidate gates must agree with the hard-failure map. For example, `decision_window_gate`, `session_liquidity_gate`, `identity_gate`, `price_action_gate`, `instrument_gate`, and `status_gate` cannot publish `PASS` when the corresponding hard-failure evidence says source-backed decision-window snapshots, official-session liquidity windows, identity quality, price-action coverage, ordinary-equity classification, or trading-status evidence are not ready. `warmup_gate` must agree with `feature_readiness`, but it does not block PIT universe interval promotion.

Likewise, `candidate_audit_status` must match the hard-failure map: it cannot publish `PASS` while any hard-failure value is active, and it cannot publish `FAIL` when no hard-failure value is active.

`earliest_candidate_gate_pass_start` must be consistent with the candidate rows. If it is `null`, no candidate row can have `CANDIDATE_GATE_PASS_INTERPRETATION`. If it is set, it must be a configured start and the earliest row whose audit status and every first-class gate are `PASS`. New Phase 3 manifests also emit `refined_earliest_candidate_gate_pass_boundary`, the earliest monthly/session boundary whose remaining interval passes universe gates after the coarse candidate scan. This boundary can be inside a coarse candidate that failed at its exact start. `candidate_recommended_pit_universe_interval` records the refined PIT-universe interval for release audit, while `candidate_recommended_research_interval` remains a fail-closed release-audit wrapper. Neither is a trusted interval unless the same range is also published in `research_quality_intervals`.

The completion audit validates `candidate_recommended_pit_universe_interval` and `candidate_recommended_research_interval` fail-closed. Their `start` values must equal `refined_earliest_candidate_gate_pass_boundary`, their status must match refined-boundary availability, their profile fields must match the published profile, their `boundary_scan_method` must equal `MONTHLY_SNAPSHOT_BOUNDARIES_WITH_OFFICIAL_SESSION_LOOKBACK`, and their `promotion_status` must remain `NOT_PROMOTED_UNLESS_PRESENT_IN_RESEARCH_QUALITY_INTERVALS`. The PIT-universe interval must publish `feature_readiness_policy = FEATURE_READINESS_REPORTED_SEPARATELY`.

`DataPlatform.from_release()` applies the same candidate interval recommendation checks during manifest loading. This prevents API consumers from using a release whose refined boundary, PIT-universe recommendation, or feature-readiness policy has gone stale even before the completion-audit report is read.

The manifest candidate decision rows must also match the generated candidate promotion audit artifact. For each configured candidate start, `candidate_audit_status`, `feature_readiness`, `refined_earliest_passing_snapshot`, and `hard_failures` in `research_release_manifest.json` must equal the corresponding row in `candidate_promotion_audit_<release>.json`. Boolean hard-failure fields must remain booleans, count fields must remain integers, and `refined_earliest_passing_snapshot` must be a string or null. A `PASS` candidate audit must have a non-null refined snapshot. The field set is published in the profile constants as `CANDIDATE_HARD_FAILURE_KEYS`.

If a candidate audit row is not recorded, the generated candidate decision remains fail-closed: boolean hard-failure fields are emitted as active failures instead of an empty map.
