from pathlib import Path


WORKFLOW = Path('.github/workflows/publish-phase3-handoff.yml')
DOC = Path('docs/github_release_storage.md')


def test_phase3_publication_is_github_release_backed_and_immutable():
    text = WORKFLOW.read_text(encoding='utf-8')
    assert 'permissions:\n  contents: write' in text
    assert 'gh release create "$RELEASE_ID"' in text
    assert 'Refusing to overwrite existing immutable release tag' in text
    assert 'gh release upload "$RELEASE_ID"' in text
    assert 'gh release download "$RELEASE_ID"' in text
    assert 'sha256sum -c' in text
    assert 'github_storage_manifest.json' in text


def test_phase3_publication_requires_core_downstream_assets():
    text = WORKFLOW.read_text(encoding='utf-8')
    for artifact in (
        'data_release_manifest.json',
        'research_release_manifest.json',
        'partitioned_artifacts_manifest.json',
        'security_master.parquet',
        'symbol_history.parquet',
        'isin_history.parquet',
        'company_name_history.parquet',
        'issuer_master.parquet',
        'listing_episodes.parquet',
        'trading_calendar.parquet',
        'trading_status_intervals.parquet',
        'research_universe_monthly.parquet',
        'required_research_security.parquet',
    ):
        assert artifact in text


def test_actions_artifacts_are_not_documented_as_source_of_truth():
    text = DOC.read_text(encoding='utf-8')
    assert 'GitHub Actions artifacts are diagnostics only' in text
    assert 'india-active-universe-raw-nse-v1' in text
    assert 'downloaded back from GitHub' in text
