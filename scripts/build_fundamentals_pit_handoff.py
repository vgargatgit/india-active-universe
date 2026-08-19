from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import duckdb

from india_active_universe.profiles import PRIORITY_SCOPE, PROFILE_ID, PROFILE_VERSION


HANDOFF_CONTRACT = "fundamentals-pit-handoff-v1"
REQUIRED_ARTIFACTS = (
    "security_master.parquet",
    "symbol_history.parquet",
    "isin_history.parquet",
    "company_name_history.parquet",
    "issuer_master.parquet",
    "listing_episodes.parquet",
    "research_universe_monthly.parquet",
    "required_research_security.parquet",
    "trading_calendar.parquet",
    "trading_status_intervals.parquet",
)
PIT_HARD_FAILURE_KEYS = (
    "not_materialized",
    "candidate_start_snapshot_missing",
    "decision_window_snapshots_missing",
    "identity_failures",
    "instrument_failures",
    "status_failures",
    "session_liquidity_window_failures",
)


class PitHandoffError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def logical_sha256(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def load_pass_invariant(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("status") != "PASS" or int(value.get("failure_count") or 0) != 0:
        raise PitHandoffError("research invariant validation is not PASS")
    return value


def _is_active_failure(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return int(value or 0) != 0


def load_pass_candidate(path: Path, candidate_start: str, research_start: str) -> dict:
    """Require the candidate's PIT-universe gate, not unrelated full-release gates.

    The narrow handoff exists specifically to let downstream consumers materialize
    historical universe membership. Full research-candidate PASS additionally
    depends on price-action and feature/model-readiness gates that belong to the
    canonical price release tracked separately by issue #2. Those results remain
    recorded in provenance but cannot veto a membership handoff when the PIT gate,
    refined boundary, and independent monthly-universe invariants all pass.
    """

    value = json.loads(path.read_text(encoding="utf-8"))
    candidates = [
        row
        for row in value.get("candidate_audits", [])
        if isinstance(row, dict) and row.get("candidate_start") == candidate_start
    ]
    if len(candidates) != 1:
        raise PitHandoffError(
            f"expected exactly one candidate audit for {candidate_start}; found {len(candidates)}"
        )
    row = candidates[0]
    hard = row.get("hard_failures") or {}
    pit_active = {
        key: hard.get(key)
        for key in PIT_HARD_FAILURE_KEYS
        if _is_active_failure(hard.get(key))
    }
    if row.get("pit_universe_gate_pass") is not True or pit_active:
        diagnostic = {
            "pit_universe_gate_pass": row.get("pit_universe_gate_pass"),
            "research_candidate_gate_pass": row.get("research_candidate_gate_pass"),
            "status": row.get("status"),
            "refined_earliest_passing_snapshot": row.get(
                "refined_earliest_passing_snapshot"
            ),
            "pit_hard_failures": pit_active,
            "all_hard_failures": hard,
            "feature_readiness": row.get("feature_readiness"),
            "price_action_evidence": row.get("price_action_evidence"),
        }
        raise PitHandoffError(
            "earliest candidate PIT-universe gate is not PASS: "
            + json.dumps(diagnostic, sort_keys=True)
        )
    if row.get("refined_earliest_passing_snapshot") != research_start:
        raise PitHandoffError(
            "candidate refined boundary does not equal the promoted handoff start: "
            f"candidate={row.get('refined_earliest_passing_snapshot')!r}, "
            f"expected={research_start!r}"
        )
    return row


def validate_monthly_release(
    release: Path,
    *,
    research_start: str,
    research_end: str,
) -> dict:
    missing = [name for name in REQUIRED_ARTIFACTS if not (release / name).is_file()]
    if missing:
        raise PitHandoffError("release is missing PIT handoff artifacts: " + ", ".join(missing))

    con = duckdb.connect()
    try:
        monthly = str((release / "research_universe_monthly.parquet").resolve())
        calendar = str((release / "trading_calendar.parquet").resolve())
        first, last, rows, securities, dates = con.execute(
            """
            SELECT MIN(CAST(date AS DATE)), MAX(CAST(date AS DATE)), COUNT(*),
                   COUNT(DISTINCT security_id), COUNT(DISTINCT CAST(date AS DATE))
            FROM read_parquet(?)
            """,
            [monthly],
        ).fetchone()
        if str(first) != research_start or str(last) != research_end:
            raise PitHandoffError(
                f"monthly PIT bounds are {first}..{last}, expected {research_start}..{research_end}"
            )
        duplicate_rows = con.execute(
            """
            SELECT COUNT(*) FROM (
              SELECT CAST(date AS DATE), security_id, COUNT(*) AS n
              FROM read_parquet(?) GROUP BY 1,2 HAVING COUNT(*) > 1
            )
            """,
            [monthly],
        ).fetchone()[0]
        if duplicate_rows:
            raise PitHandoffError(f"monthly PIT artifact has {duplicate_rows} duplicate date/security keys")
        profile_mismatch = con.execute(
            """
            SELECT COUNT(*) FROM read_parquet(?)
            WHERE profile_id IS DISTINCT FROM ? OR profile_version IS DISTINCT FROM ?
            """,
            [monthly, PROFILE_ID, PROFILE_VERSION],
        ).fetchone()[0]
        if profile_mismatch:
            raise PitHandoffError(f"monthly PIT artifact has {profile_mismatch} profile mismatches")
        cadence_failures = con.execute(
            """
            WITH expected AS (
              SELECT DATE_TRUNC('month', CAST(date AS DATE)) AS month,
                     MAX(CAST(date AS DATE)) AS expected_date
              FROM read_parquet(?)
              WHERE CAST(date AS DATE) BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
              GROUP BY 1
            ), actual AS (
              SELECT DATE_TRUNC('month', CAST(date AS DATE)) AS month,
                     COUNT(DISTINCT CAST(date AS DATE)) AS actual_dates,
                     MIN(CAST(date AS DATE)) AS actual_date
              FROM read_parquet(?)
              GROUP BY 1
            )
            SELECT COUNT(*) FROM expected e
            FULL OUTER JOIN actual a USING (month)
            WHERE a.actual_dates IS DISTINCT FROM 1
               OR a.actual_date IS DISTINCT FROM e.expected_date
            """,
            [calendar, research_start, research_end, monthly],
        ).fetchone()[0]
        if cadence_failures:
            raise PitHandoffError(f"monthly PIT cadence has {cadence_failures} invalid/missing months")
        eligible = con.execute(
            "SELECT COUNT(*) FROM read_parquet(?) WHERE NSE_BROAD_LIQUID_PIT_V1_eligible",
            [monthly],
        ).fetchone()[0]
        eligible_missing_rank = con.execute(
            """
            SELECT COUNT(*) FROM read_parquet(?)
            WHERE NSE_BROAD_LIQUID_PIT_V1_eligible AND liquidity_rank_126 IS NULL
            """,
            [monthly],
        ).fetchone()[0]
        required = con.execute(
            "SELECT COUNT(*) FROM read_parquet(?)",
            [str((release / "required_research_security.parquet").resolve())],
        ).fetchone()[0]
    finally:
        con.close()
    return {
        "first_snapshot": str(first),
        "last_snapshot": str(last),
        "monthly_rows": int(rows),
        "monthly_snapshot_count": int(dates),
        "monthly_unique_securities": int(securities),
        "eligible_rows": int(eligible),
        "eligible_missing_liquidity_rank": int(eligible_missing_rank),
        "required_research_security_rows": int(required),
    }


def build_handoff(
    *,
    release: Path,
    invariant: Path,
    candidate_audit: Path,
    source_manifest: Path,
    corporate_action_source_manifest: Path,
    suspension_source_manifest: Path | None,
    output: Path,
    handoff_id: str,
    research_start: str,
    research_end: str,
    candidate_start: str,
) -> dict:
    load_pass_invariant(invariant)
    candidate = load_pass_candidate(candidate_audit, candidate_start, research_start)
    coverage = validate_monthly_release(
        release, research_start=research_start, research_end=research_end
    )
    output_release = output / "release"
    if output.exists():
        raise PitHandoffError(f"immutable handoff target already exists: {output}")
    output_release.mkdir(parents=True)
    for name in REQUIRED_ARTIFACTS:
        shutil.copy2(release / name, output_release / name)

    artifacts = {
        f"release/{name}": sha256_file(output_release / name)
        for name in REQUIRED_ARTIFACTS
    }
    provenance = {
        "build_git_commit": git_commit(),
        "source_manifest_sha256": sha256_file(source_manifest),
        "corporate_action_source_manifest_sha256": sha256_file(
            corporate_action_source_manifest
        ),
        "suspension_source_manifest_sha256": (
            sha256_file(suspension_source_manifest)
            if suspension_source_manifest and suspension_source_manifest.is_file()
            else None
        ),
        "research_invariant_validation_sha256": sha256_file(invariant),
        "candidate_promotion_audit_sha256": sha256_file(candidate_audit),
        "candidate_start": candidate_start,
        "candidate_refined_boundary": candidate["refined_earliest_passing_snapshot"],
        "candidate_pit_universe_gate_pass": candidate.get("pit_universe_gate_pass"),
        "candidate_research_gate_pass": candidate.get("research_candidate_gate_pass"),
        "candidate_overall_status": candidate.get("status"),
        "candidate_feature_readiness": candidate.get("feature_readiness"),
        "candidate_price_action_evidence": candidate.get("price_action_evidence"),
        "candidate_all_hard_failures": candidate.get("hard_failures"),
    }
    data_manifest = {
        "release_id": handoff_id,
        "project_id": "india-active-universe",
        "build_mode": "PIT_UNIVERSE_HANDOFF_REBUILD",
        "git_commit": provenance["build_git_commit"],
        "research_coverage": {
            "research_verified_start": research_start,
            "research_verified_end": research_end,
            "monthly_snapshot_start": research_start,
            "universe_profile": PROFILE_ID,
            "profile_version": PROFILE_VERSION,
            "priority_scope": PRIORITY_SCOPE,
        },
        "research_quality_intervals": [
            {
                "start": research_start,
                "end": research_end,
                "status": "RESEARCH_HIGH_CONFIDENCE",
                "profile": PROFILE_ID,
                "profile_version": PROFILE_VERSION,
                "priority_scope": PRIORITY_SCOPE,
                "interval_type": "PIT_UNIVERSE",
                "feature_readiness_policy": "FEATURE_READINESS_REPORTED_SEPARATELY",
            }
        ],
        "artifacts": artifacts,
        "coverage": coverage,
        "provenance": provenance,
    }
    research_manifest = {
        "release_id": handoff_id,
        "project_id": "india-active-universe",
        "research_quality": {
            "start": research_start,
            "end": research_end,
            "status": "RESEARCH_HIGH_CONFIDENCE",
            "universe_profile": PROFILE_ID,
            "profile_version": PROFILE_VERSION,
            "priority_scope": PRIORITY_SCOPE,
            "interval_type": "PIT_UNIVERSE",
            "feature_readiness_policy": "FEATURE_READINESS_REPORTED_SEPARATELY",
        },
        "artifacts": artifacts,
        "coverage": coverage,
        "provenance": provenance,
    }
    (output / "data_release_manifest.json").write_text(
        json.dumps(data_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "research_release_manifest.json").write_text(
        json.dumps(research_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    handoff_manifest = {
        "contract": HANDOFF_CONTRACT,
        "handoff_id": handoff_id,
        "profile_id": PROFILE_ID,
        "profile_version": PROFILE_VERSION,
        "priority_scope": PRIORITY_SCOPE,
        "research_start": research_start,
        "research_end": research_end,
        "coverage": coverage,
        "provenance": provenance,
        "artifacts": artifacts,
        "data_release_manifest_sha256": sha256_file(output / "data_release_manifest.json"),
        "research_release_manifest_sha256": sha256_file(output / "research_release_manifest.json"),
    }
    handoff_manifest["logical_content_sha256"] = logical_sha256(handoff_manifest)
    (output / "fundamentals_pit_handoff_manifest.json").write_text(
        json.dumps(handoff_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return handoff_manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--invariant", required=True)
    parser.add_argument("--candidate-audit", required=True)
    parser.add_argument("--source-manifest", required=True)
    parser.add_argument("--corporate-action-source-manifest", required=True)
    parser.add_argument("--suspension-source-manifest")
    parser.add_argument("--output", required=True)
    parser.add_argument("--handoff-id", default="india_active_universe_fundamentals_pit_v1")
    parser.add_argument("--research-start", default="2006-01-31")
    parser.add_argument("--research-end", default="2026-08-10")
    parser.add_argument("--candidate-start", default="2006-01-01")
    args = parser.parse_args()
    result = build_handoff(
        release=Path(args.release),
        invariant=Path(args.invariant),
        candidate_audit=Path(args.candidate_audit),
        source_manifest=Path(args.source_manifest),
        corporate_action_source_manifest=Path(args.corporate_action_source_manifest),
        suspension_source_manifest=(Path(args.suspension_source_manifest) if args.suspension_source_manifest else None),
        output=Path(args.output),
        handoff_id=args.handoff_id,
        research_start=args.research_start,
        research_end=args.research_end,
        candidate_start=args.candidate_start,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
