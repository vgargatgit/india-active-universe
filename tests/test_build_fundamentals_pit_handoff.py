from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/build_fundamentals_pit_handoff.py"
SPEC = importlib.util.spec_from_file_location("build_fundamentals_pit_handoff", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load {SCRIPT}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

PitHandoffError = MODULE.PitHandoffError
load_pass_candidate = MODULE.load_pass_candidate


def candidate_payload(**overrides):
    row = {
        "candidate_start": "2006-01-01",
        "refined_earliest_passing_snapshot": "2006-01-31",
        "pit_universe_gate_pass": True,
        "research_candidate_gate_pass": False,
        "status": "FAIL",
        "hard_failures": {
            "not_materialized": False,
            "candidate_start_snapshot_missing": False,
            "decision_window_snapshots_missing": False,
            "identity_failures": 0,
            "instrument_failures": 0,
            "status_failures": 0,
            "session_liquidity_window_failures": 0,
            "price_adjustment_failures": 4,
            "material_missing_factors": 0,
            "contaminating_signal_window_non_pass_boundaries": 2,
        },
        "feature_readiness": {"feature_warmup_not_ready": False},
        "price_action_evidence": {
            "price_action_gate_pass": False,
            "boundary_validation_review_required": True,
        },
    }
    row.update(overrides)
    return {"candidate_audits": [row]}


def write_payload(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_narrow_handoff_accepts_pit_pass_even_when_full_research_gate_fails(
    tmp_path: Path,
) -> None:
    path = write_payload(tmp_path, candidate_payload())
    row = load_pass_candidate(path, "2006-01-01", "2006-01-31")
    assert row["pit_universe_gate_pass"] is True
    assert row["research_candidate_gate_pass"] is False
    assert row["status"] == "FAIL"


def test_narrow_handoff_rejects_any_pit_hard_failure(tmp_path: Path) -> None:
    payload = candidate_payload()
    payload["candidate_audits"][0]["hard_failures"]["identity_failures"] = 1
    payload["candidate_audits"][0]["pit_universe_gate_pass"] = False
    path = write_payload(tmp_path, payload)
    with pytest.raises(PitHandoffError, match="identity_failures"):
        load_pass_candidate(path, "2006-01-01", "2006-01-31")


def test_narrow_handoff_rejects_shifted_refined_boundary(tmp_path: Path) -> None:
    path = write_payload(
        tmp_path,
        candidate_payload(refined_earliest_passing_snapshot="2006-02-28"),
    )
    with pytest.raises(PitHandoffError, match="refined boundary"):
        load_pass_candidate(path, "2006-01-01", "2006-01-31")
