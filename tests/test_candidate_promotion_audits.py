import json
import subprocess
import sys

import pyarrow as pa
import pyarrow.parquet as pq

from india_active_universe.profiles import (
    CANDIDATE_RESEARCH_START_DATES,
    CORPORATE_ACTION_BOUNDARY_ARTIFACT,
    CORPORATE_ACTIONS_ARTIFACT,
    LIQUIDITY_ARTIFACT,
    PROFILE_ID,
    PROFILE_VERSION,
    PRIORITY_SCOPE,
    RESEARCH_UNIVERSE_MONTHLY_ARTIFACT,
    TRADING_CALENDAR_ARTIFACT,
)
from scripts.build_completion_audit import EXPECTED_CANDIDATE_HARD_FAILURE_KEYS


def test_candidate_promotion_audit_emits_all_configured_candidates(tmp_path):
    release = tmp_path / "release"
    release.mkdir()
    pq.write_table(
        pa.table(
            {
                "date": ["2006-01-31", "2007-01-31", "2009-01-30", "2011-01-31"],
                "security_id": ["SEC1", "SEC1", "SEC1", "SEC1"],
                "NSE_BROAD_LIQUID_PIT_V1_eligible": [True, True, True, True],
                "top750_liquidity": [True, True, True, True],
                "research_identity_ok": [True, True, True, True],
                "price_adjustment_ok": [True, True, True, True],
                "instrument_type": ["ORDINARY_EQUITY", "ORDINARY_EQUITY", "ORDINARY_EQUITY", "ORDINARY_EQUITY"],
                "instrument_type_quality": ["OFFICIAL_REFERENCE", "OFFICIAL_REFERENCE", "OFFICIAL_REFERENCE", "OFFICIAL_REFERENCE"],
                "status_quality": ["OBSERVED_OFFICIAL_TRADE", "OBSERVED_OFFICIAL_TRADE", "OBSERVED_OFFICIAL_TRADE", "OBSERVED_OFFICIAL_TRADE"],
                "model_handoff_history_ready_300": [False, True, True, True],
                "signal_history_ready_252": [True, True, True, True],
                "signal_history_ready_273": [True, True, True, True],
            }
        ),
        release / RESEARCH_UNIVERSE_MONTHLY_ARTIFACT,
    )
    pq.write_table(
        pa.table(
            {
                "date": ["2006-01-02", "2006-01-31", "2007-01-02", "2007-01-31", "2009-01-01", "2009-01-30", "2011-01-03", "2011-01-31"],
                "session_index": [0, 19, 250, 269, 750, 769, 1250, 1268],
            }
        ),
        release / TRADING_CALENDAR_ARTIFACT,
    )
    pq.write_table(
        pa.table(
            {
                "date": ["2006-01-31", "2007-01-31", "2009-01-30", "2011-01-31"],
                "security_id": ["SEC1", "SEC1", "SEC1", "SEC1"],
                "liquidity_window_definition": ["OFFICIAL_NSE_SESSION_WINDOW", "OFFICIAL_NSE_SESSION_WINDOW", "OFFICIAL_NSE_SESSION_WINDOW", "OFFICIAL_NSE_SESSION_WINDOW"],
            }
        ),
        release / LIQUIDITY_ARTIFACT,
    )
    pq.write_table(
        pa.table(
            {
                "event_id": pa.array([], type=pa.string()),
                "security_id": pa.array([], type=pa.string()),
                "event_date": pa.array([], type=pa.string()),
                "event_type": pa.array([], type=pa.string()),
                "price_factor": pa.array([], type=pa.float64()),
                "share_factor": pa.array([], type=pa.float64()),
            }
        ),
        release / CORPORATE_ACTIONS_ARTIFACT,
    )
    pq.write_table(
        pa.table(
            {
                "event_id": pa.array([], type=pa.string()),
                "security_id": pa.array([], type=pa.string()),
                "ex_date": pa.array([], type=pa.string()),
                "validation_status": pa.array([], type=pa.string()),
            }
        ),
        release / CORPORATE_ACTION_BOUNDARY_ARTIFACT,
    )
    out = tmp_path / "candidate_audit.json"

    result = subprocess.run(
        [sys.executable, "scripts/build_candidate_promotion_audits.py", "--release", str(release), "--out", str(out)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["profile"] == PROFILE_ID
    assert report["profile_version"] == PROFILE_VERSION
    assert report["priority_scope"] == PRIORITY_SCOPE
    assert report["candidate_start_dates"] == list(CANDIDATE_RESEARCH_START_DATES)
    audits = report["candidate_audits"]
    assert {row["candidate_start"] for row in audits} == set(CANDIDATE_RESEARCH_START_DATES)
    assert all(row["profile"] == PROFILE_ID for row in audits)
    assert all(row["profile_version"] == PROFILE_VERSION for row in audits)
    assert all(row["priority_scope"] == PRIORITY_SCOPE for row in audits)
    assert all(set(row["hard_failures"]) == EXPECTED_CANDIDATE_HARD_FAILURE_KEYS for row in audits)
    assert all(row["monthly_snapshots_after_decision"] > 0 for row in audits)
    assert any(row["required_rows"] > row["fully_warmed_required_rows"] for row in audits)
    assert any(row["feature_readiness"]["feature_warmup_not_ready"] is True for row in audits)
    assert all(row["pit_universe_gate_pass"] is True for row in audits)
    assert any(row["feature_model_readiness_complete"] is False for row in audits)
    assert all(row["hard_failures"]["candidate_start_snapshot_missing"] is False for row in audits)
    assert all(row["hard_failures"]["decision_window_snapshots_missing"] is False for row in audits)
    assert all(row["hard_failures"]["session_liquidity_window_failures"] == 0 for row in audits)
    assert all(row["refined_earliest_passing_snapshot"] is not None for row in audits)
    assert all(row["status"] == ("PASS" if row["research_candidate_gate_pass"] else "FAIL") for row in audits)
    assert any(row["status"] == "FAIL" for row in audits)
