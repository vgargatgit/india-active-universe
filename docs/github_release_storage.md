# Durable GitHub storage contract

The Phase 3 downstream handoff is stored in **GitHub Releases**, not in ephemeral Actions artifacts and not only as manifests in ordinary Git.

## Canonical release

The canonical downstream release tag is the `release_id` recorded by both `data_release_manifest.json` and `research_release_manifest.json` (currently targeted as `india_equity_data_v2.2.9`). A release is immutable: the publication workflow refuses to overwrite an existing tag.

Each canonical GitHub Release contains:

- `<release_id>-complete.tar.gz.part-NNN` — ordered chunks of the complete materialized release directory plus release-specific audit evidence; chunks are capped below the GitHub Release per-asset size bound;
- `<release_id>-complete.parts.sha256` — SHA-256 for every uploaded chunk;
- `<release_id>-complete.tar.gz.sha256` — SHA-256 for the reconstructed complete archive;
- directly downloadable downstream artifacts: `data_release_manifest.json`, `research_release_manifest.json`, `partitioned_artifacts_manifest.json`, identity artifacts, trading calendar/status artifacts, `research_universe_monthly.parquet`, and `required_research_security.parquet`.

Concatenating the ordered `part-NNN` files reconstructs `<release_id>-complete.tar.gz`. The complete archive contains `github_storage_manifest.json`. Every archived file has an exact relative path, byte count, and SHA-256. Publication succeeds only after every chunk is downloaded back from GitHub, the complete archive is reconstructed and verified, and every archived entry is re-hashed successfully.

The complete archive intentionally includes the full release directory rather than only the small downstream subset. This retains all Parquet outputs and year-partitioned sidecars created by `build_partitioned_release_artifacts.py`.

## Raw NSE market history

Official NSE bhavcopies are retained separately under GitHub Release tag `india-active-universe-raw-nse-v1` as immutable year generations:

`nse-bhavcopy-<YEAR>-run-<GITHUB_RUN_ID>-attempt-<GITHUB_RUN_ATTEMPT>.tar.gz`

Every generation contains the raw official archives for that year and `year_manifest.json`. Restore verifies the SHA-256 manifest before any file is reused. A later generation never deletes or overwrites an earlier generation.

GitHub Actions artifacts are diagnostics only. They are not a source of truth for the release or raw history.

## Required publication gates

`.github/workflows/publish-phase3-handoff.yml` refuses publication unless:

1. every `REQUIRED_RELEASE_ARTIFACTS` file exists;
2. both release manifests identify the requested release ID;
3. the release-specific completion audit and research-invariant report exist;
4. research invariants are `PASS`;
5. `validate_release_manifest_hashes.py` verifies the materialized release;
6. the GitHub Release tag does not already exist;
7. the uploaded chunks and reconstructed complete archive pass a download-and-rehash round trip.

These gates are intentionally fail-closed. Missing historical source data must be reacquired or explicitly recovered; hashes or quality gates must never be relaxed merely to create a release.

## Downstream consumption

`india-funda` should pin:

- the canonical release ID;
- the SHA-256 of `data_release_manifest.json`;
- the SHA-256 of `research_release_manifest.json`;
- the upstream profile/version and accepted research-quality interval.

Consumers may download the small Parquet assets directly from the GitHub Release or fetch the complete archive chunks and verify `github_storage_manifest.json`. They should never depend on an Actions artifact retention window.
