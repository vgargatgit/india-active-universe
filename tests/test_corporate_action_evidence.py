from pathlib import Path

from scripts.validate_corporate_action_evidence import evidence_audit, sha256


def write_yaml(path: Path, text: str) -> None:
    path.write_text(text.strip() + "\n", encoding="utf-8")


def valid_evidence(path: Path) -> None:
    write_yaml(
        path,
        """
        evidence:
          - evidence_id: CAE_TEST_01
            event_id: NSE_CA_TEST
            symbol: TEST
            event_date: 2010-01-01
            source_type: OFFICIAL_NSE_RECORD
            publisher: NSE
            source_url: https://example.com/nse-ca-test
            accessed_at: 2026-08-12
            facts:
              split_ratio: 2-for-1
            evidence_quality: OFFICIAL_NSE_RECORD
        """,
    )


def valid_resolution(path: Path, refs: str = "CAE_TEST_01") -> None:
    write_yaml(
        path,
        f"""
        resolutions:
          - event_id: NSE_CA_TEST
            symbol: TEST
            event_date: 2010-01-01
            resolution_type: VERIFIED_FACTOR_GENUINE_MARKET_MOVE
            review_status: APPROVED
            evidence_references:
              - {refs}
            rationale: verified factor
        """,
    )


def test_unknown_evidence_id_fails(tmp_path: Path):
    evidence = tmp_path / "evidence.yaml"
    resolutions = tmp_path / "resolutions.yaml"
    valid_evidence(evidence)
    valid_resolution(resolutions, "CAE_MISSING")

    summary = evidence_audit(resolutions, evidence)

    assert summary["status"] == "FAIL"
    assert summary["unresolved_evidence_id_count"] == 1


def test_approved_resolution_requires_url_backed_evidence(tmp_path: Path):
    evidence = tmp_path / "evidence.yaml"
    resolutions = tmp_path / "resolutions.yaml"
    valid_resolution(resolutions)
    write_yaml(
        evidence,
        """
        evidence:
          - evidence_id: CAE_TEST_01
            event_id: NSE_CA_TEST
            symbol: TEST
            event_date: 2010-01-01
            source_type: OFFICIAL_NSE_RECORD
            publisher: NSE
            source_url: prose-only-reference
            accessed_at: 2026-08-12
            facts:
              split_ratio: 2-for-1
            evidence_quality: OFFICIAL_NSE_RECORD
        """,
    )

    summary = evidence_audit(resolutions, evidence)

    assert summary["status"] == "FAIL"
    assert summary["missing_url_count"] == 1


def test_modified_evidence_registry_changes_hash(tmp_path: Path):
    evidence = tmp_path / "evidence.yaml"
    valid_evidence(evidence)
    first = sha256(evidence)

    evidence.write_text(evidence.read_text(encoding="utf-8").replace("2-for-1", "3-for-1"), encoding="utf-8")

    assert sha256(evidence) != first
