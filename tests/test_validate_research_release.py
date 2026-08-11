import json
import subprocess
import sys

import pyarrow as pa
import pyarrow.parquet as pq

from india_active_universe.profiles import (
    RAW_EXECUTION_PRICE_ARTIFACT,
    RESEARCH_UNIVERSE_MONTHLY_ARTIFACT,
    TRADING_CALENDAR_ARTIFACT,
)


def _write_release(release, required_security_ids):
    release.mkdir()
    monthly = pa.table(
        {
            "date": ["2020-03-31"],
            "security_id": ["SEC1"],
            "listing_episode_id": ["LE1"],
            "symbol_at_date": ["ABC"],
            "instrument_type": ["ORDINARY_EQUITY"],
            "identity_quality": ["RECONSTRUCTED_TRADING_IDENTITY"],
            "active": [True],
            "trading_status": ["ACTIVE_TRADING"],
            "research_identity_ok": [True],
            "price_adjustment_quality": ["NO_ADJUSTMENT_REQUIRED"],
            "price_adjustment_ok": [True],
            "status_quality": ["OBSERVED_OFFICIAL_TRADE"],
            "price": [100.0],
            "history_sessions": [300],
            "listing_age_sessions": [300],
            "positive_volume_days_60": [50],
            "median_traded_value_60": [10_000_000.0],
            "median_traded_value_126": [12_000_000.0],
            "liquidity_rank_126": [700],
            "rank_126": [700],
            "liquidity_percentile": [0.7],
            "liquidity_percentile_126": [0.7],
            "LIQUID_V1_eligible": [True],
            "NSE_BROAD_LIQUID_PIT_V1_eligible": [True],
            "top500_liquidity": [False],
            "top750_liquidity": [True],
            "top1000_liquidity": [True],
            "profile_id": ["NSE_BROAD_LIQUID_PIT_V1"],
            "profile_version": ["LIQUID_V1"],
            "as_of_date": ["2020-03-31"],
            "eligibility_result": ["ELIGIBLE"],
            "eligibility_reason_codes": ["PASSED_LIQUID_V1"],
        }
    )
    pq.write_table(monthly, release / RESEARCH_UNIVERSE_MONTHLY_ARTIFACT)
    pq.write_table(pa.table({"security_id": ["SEC1"], "date": ["2020-01-01"]}), release / RAW_EXECUTION_PRICE_ARTIFACT)
    pq.write_table(pa.table({"date": ["2020-03-31"]}), release / TRADING_CALENDAR_ARTIFACT)
    pq.write_table(
        pa.table(
            {
                "security_id": required_security_ids,
                "enters_liquid_v1": [True for _ in required_security_ids],
                "enters_top750": [True for _ in required_security_ids],
                "first_research_date": ["2020-03-31" for _ in required_security_ids],
                "last_research_date": ["2020-03-31" for _ in required_security_ids],
                "research_identity_quality": ["RECONSTRUCTED_TRADING_IDENTITY" for _ in required_security_ids],
                "price_adjustment_quality": ["NO_ADJUSTMENT_REQUIRED" for _ in required_security_ids],
                "price_adjustment_ok": [True for _ in required_security_ids],
                "status_quality": ["OBSERVED_OFFICIAL_TRADE" for _ in required_security_ids],
                "active_trading_ok": [True for _ in required_security_ids],
                "instrument_type": ["ORDINARY_EQUITY" for _ in required_security_ids],
                "instrument_type_quality": ["OFFICIAL_REFERENCE" for _ in required_security_ids],
                "best_rank_126": [700 for _ in required_security_ids],
                "worst_rank_126": [700 for _ in required_security_ids],
                "max_median_traded_value_60": [10_000_000.0 for _ in required_security_ids],
                "max_median_traded_value_126": [12_000_000.0 for _ in required_security_ids],
                "max_positive_volume_days_60": [50 for _ in required_security_ids],
            }
        ),
        release / "required_research_security.parquet",
    )


def test_research_release_validator_fails_when_required_artifact_misses_monthly_required_security(tmp_path):
    release = tmp_path / "release"
    _write_release(release, [])
    out = tmp_path / "validation.json"

    result = subprocess.run(
        [sys.executable, "scripts/validate_research_release.py", "--release", str(release), "--out", str(out)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    metrics = json.loads(out.read_text(encoding="utf-8"))
    assert metrics["required_scope_missing_from_required_artifact"] == 1
    assert metrics["status"] == "FAIL"


def test_research_release_validator_accepts_matching_required_artifact(tmp_path):
    release = tmp_path / "release"
    _write_release(release, ["SEC1"])
    out = tmp_path / "validation.json"

    result = subprocess.run(
        [sys.executable, "scripts/validate_research_release.py", "--release", str(release), "--out", str(out)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    metrics = json.loads(out.read_text(encoding="utf-8"))
    assert metrics["required_scope_missing_from_required_artifact"] == 0
    assert metrics["required_artifact_security_without_monthly_scope"] == 0
    assert metrics["required_artifact_flag_failures"] == 0
    assert metrics["required_artifact_identity_quality_failures"] == 0
    assert metrics["required_artifact_price_adjustment_failures"] == 0
    assert metrics["required_artifact_status_failures"] == 0
    assert metrics["required_artifact_instrument_classification_failures"] == 0
    assert metrics["required_artifact_rank_evidence_failures"] == 0
    assert metrics["required_artifact_liquidity_evidence_failures"] == 0
    assert metrics["status"] == "PASS"


def test_research_release_validator_fails_when_required_artifact_has_extra_security(tmp_path):
    release = tmp_path / "release"
    _write_release(release, ["SEC1", "EXTRA"])
    out = tmp_path / "validation.json"

    result = subprocess.run(
        [sys.executable, "scripts/validate_research_release.py", "--release", str(release), "--out", str(out)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    metrics = json.loads(out.read_text(encoding="utf-8"))
    assert metrics["required_artifact_security_without_monthly_scope"] == 1
    assert metrics["status"] == "FAIL"


def test_research_release_validator_fails_when_required_artifact_flags_mismatch_monthly_scope(tmp_path):
    release = tmp_path / "release"
    _write_release(release, ["SEC1"])
    pq.write_table(
        pa.table(
            {
                "security_id": ["SEC1"],
                "enters_liquid_v1": [False],
                "enters_top750": [True],
                "first_research_date": ["2020-03-31"],
                "last_research_date": ["2020-03-31"],
                "research_identity_quality": ["RECONSTRUCTED_TRADING_IDENTITY"],
                "price_adjustment_quality": ["NO_ADJUSTMENT_REQUIRED"],
                "price_adjustment_ok": [True],
                "status_quality": ["OBSERVED_OFFICIAL_TRADE"],
                "active_trading_ok": [True],
                "instrument_type": ["ORDINARY_EQUITY"],
                "instrument_type_quality": ["OFFICIAL_REFERENCE"],
                "best_rank_126": [700],
                "worst_rank_126": [700],
                "max_median_traded_value_60": [10_000_000.0],
                "max_median_traded_value_126": [12_000_000.0],
                "max_positive_volume_days_60": [50],
            }
        ),
        release / "required_research_security.parquet",
    )
    out = tmp_path / "validation.json"

    result = subprocess.run(
        [sys.executable, "scripts/validate_research_release.py", "--release", str(release), "--out", str(out)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    metrics = json.loads(out.read_text(encoding="utf-8"))
    assert metrics["required_artifact_flag_failures"] == 1
    assert metrics["status"] == "FAIL"


def test_research_release_validator_fails_when_required_artifact_date_range_mismatches_monthly_scope(tmp_path):
    release = tmp_path / "release"
    _write_release(release, ["SEC1"])
    pq.write_table(
        pa.table(
            {
                "security_id": ["SEC1"],
                "enters_liquid_v1": [True],
                "enters_top750": [True],
                "first_research_date": ["2020-01-31"],
                "last_research_date": ["2020-03-31"],
                "research_identity_quality": ["RECONSTRUCTED_TRADING_IDENTITY"],
                "price_adjustment_quality": ["NO_ADJUSTMENT_REQUIRED"],
                "price_adjustment_ok": [True],
                "status_quality": ["OBSERVED_OFFICIAL_TRADE"],
                "active_trading_ok": [True],
                "instrument_type": ["ORDINARY_EQUITY"],
                "instrument_type_quality": ["OFFICIAL_REFERENCE"],
                "best_rank_126": [700],
                "worst_rank_126": [700],
                "max_median_traded_value_60": [10_000_000.0],
                "max_median_traded_value_126": [12_000_000.0],
                "max_positive_volume_days_60": [50],
            }
        ),
        release / "required_research_security.parquet",
    )
    out = tmp_path / "validation.json"

    result = subprocess.run(
        [sys.executable, "scripts/validate_research_release.py", "--release", str(release), "--out", str(out)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    metrics = json.loads(out.read_text(encoding="utf-8"))
    assert metrics["required_artifact_date_range_failures"] == 1
    assert metrics["status"] == "FAIL"


def test_research_release_validator_fails_when_required_artifact_identity_quality_is_not_research_ok(tmp_path):
    release = tmp_path / "release"
    _write_release(release, ["SEC1"])
    pq.write_table(
        pa.table(
            {
                "security_id": ["SEC1"],
                "enters_liquid_v1": [True],
                "enters_top750": [True],
                "first_research_date": ["2020-03-31"],
                "last_research_date": ["2020-03-31"],
                "research_identity_quality": ["PARTIAL"],
                "price_adjustment_quality": ["NO_ADJUSTMENT_REQUIRED"],
                "price_adjustment_ok": [True],
                "status_quality": ["OBSERVED_OFFICIAL_TRADE"],
                "active_trading_ok": [True],
                "instrument_type": ["ORDINARY_EQUITY"],
                "instrument_type_quality": ["OFFICIAL_REFERENCE"],
                "best_rank_126": [700],
                "worst_rank_126": [700],
                "max_median_traded_value_60": [10_000_000.0],
                "max_median_traded_value_126": [12_000_000.0],
                "max_positive_volume_days_60": [50],
            }
        ),
        release / "required_research_security.parquet",
    )
    out = tmp_path / "validation.json"

    result = subprocess.run(
        [sys.executable, "scripts/validate_research_release.py", "--release", str(release), "--out", str(out)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    metrics = json.loads(out.read_text(encoding="utf-8"))
    assert metrics["required_artifact_identity_quality_failures"] == 1
    assert metrics["status"] == "FAIL"


def test_research_release_validator_fails_when_required_artifact_price_adjustment_is_not_ok(tmp_path):
    release = tmp_path / "release"
    _write_release(release, ["SEC1"])
    pq.write_table(
        pa.table(
            {
                "security_id": ["SEC1"],
                "enters_liquid_v1": [True],
                "enters_top750": [True],
                "first_research_date": ["2020-03-31"],
                "last_research_date": ["2020-03-31"],
                "research_identity_quality": ["RECONSTRUCTED_TRADING_IDENTITY"],
                "price_adjustment_quality": ["UNRESOLVED_CORPORATE_ACTION"],
                "price_adjustment_ok": [False],
                "status_quality": ["OBSERVED_OFFICIAL_TRADE"],
                "active_trading_ok": [True],
                "instrument_type": ["ORDINARY_EQUITY"],
                "instrument_type_quality": ["OFFICIAL_REFERENCE"],
                "best_rank_126": [700],
                "worst_rank_126": [700],
                "max_median_traded_value_60": [10_000_000.0],
                "max_median_traded_value_126": [12_000_000.0],
                "max_positive_volume_days_60": [50],
            }
        ),
        release / "required_research_security.parquet",
    )
    out = tmp_path / "validation.json"

    result = subprocess.run(
        [sys.executable, "scripts/validate_research_release.py", "--release", str(release), "--out", str(out)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    metrics = json.loads(out.read_text(encoding="utf-8"))
    assert metrics["required_artifact_price_adjustment_failures"] == 1
    assert metrics["status"] == "FAIL"


def test_research_release_validator_fails_when_required_artifact_status_is_not_active(tmp_path):
    release = tmp_path / "release"
    _write_release(release, ["SEC1"])
    pq.write_table(
        pa.table(
            {
                "security_id": ["SEC1"],
                "enters_liquid_v1": [True],
                "enters_top750": [True],
                "first_research_date": ["2020-03-31"],
                "last_research_date": ["2020-03-31"],
                "research_identity_quality": ["RECONSTRUCTED_TRADING_IDENTITY"],
                "price_adjustment_quality": ["NO_ADJUSTMENT_REQUIRED"],
                "price_adjustment_ok": [True],
                "status_quality": ["UNKNOWN_STATUS"],
                "active_trading_ok": [False],
                "instrument_type": ["ORDINARY_EQUITY"],
                "instrument_type_quality": ["OFFICIAL_REFERENCE"],
                "best_rank_126": [700],
                "worst_rank_126": [700],
                "max_median_traded_value_60": [10_000_000.0],
                "max_median_traded_value_126": [12_000_000.0],
                "max_positive_volume_days_60": [50],
            }
        ),
        release / "required_research_security.parquet",
    )
    out = tmp_path / "validation.json"

    result = subprocess.run(
        [sys.executable, "scripts/validate_research_release.py", "--release", str(release), "--out", str(out)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    metrics = json.loads(out.read_text(encoding="utf-8"))
    assert metrics["required_artifact_status_failures"] == 1
    assert metrics["status"] == "FAIL"


def test_research_release_validator_fails_when_required_artifact_instrument_classification_is_unresolved(tmp_path):
    release = tmp_path / "release"
    _write_release(release, ["SEC1"])
    pq.write_table(
        pa.table(
            {
                "security_id": ["SEC1"],
                "enters_liquid_v1": [True],
                "enters_top750": [True],
                "first_research_date": ["2020-03-31"],
                "last_research_date": ["2020-03-31"],
                "research_identity_quality": ["RECONSTRUCTED_TRADING_IDENTITY"],
                "price_adjustment_quality": ["NO_ADJUSTMENT_REQUIRED"],
                "price_adjustment_ok": [True],
                "status_quality": ["OBSERVED_OFFICIAL_TRADE"],
                "active_trading_ok": [True],
                "instrument_type": ["ETF"],
                "instrument_type_quality": ["UNRESOLVED"],
                "best_rank_126": [700],
                "worst_rank_126": [700],
                "max_median_traded_value_60": [10_000_000.0],
                "max_median_traded_value_126": [12_000_000.0],
                "max_positive_volume_days_60": [50],
            }
        ),
        release / "required_research_security.parquet",
    )
    out = tmp_path / "validation.json"

    result = subprocess.run(
        [sys.executable, "scripts/validate_research_release.py", "--release", str(release), "--out", str(out)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    metrics = json.loads(out.read_text(encoding="utf-8"))
    assert metrics["required_artifact_instrument_classification_failures"] == 1
    assert metrics["status"] == "FAIL"


def test_research_release_validator_fails_when_required_artifact_rank_evidence_mismatches_monthly_scope(tmp_path):
    release = tmp_path / "release"
    _write_release(release, ["SEC1"])
    pq.write_table(
        pa.table(
            {
                "security_id": ["SEC1"],
                "enters_liquid_v1": [True],
                "enters_top750": [True],
                "first_research_date": ["2020-03-31"],
                "last_research_date": ["2020-03-31"],
                "research_identity_quality": ["RECONSTRUCTED_TRADING_IDENTITY"],
                "price_adjustment_quality": ["NO_ADJUSTMENT_REQUIRED"],
                "price_adjustment_ok": [True],
                "status_quality": ["OBSERVED_OFFICIAL_TRADE"],
                "active_trading_ok": [True],
                "instrument_type": ["ORDINARY_EQUITY"],
                "instrument_type_quality": ["OFFICIAL_REFERENCE"],
                "best_rank_126": [650],
                "worst_rank_126": [700],
                "max_median_traded_value_60": [10_000_000.0],
                "max_median_traded_value_126": [12_000_000.0],
                "max_positive_volume_days_60": [50],
            }
        ),
        release / "required_research_security.parquet",
    )
    out = tmp_path / "validation.json"

    result = subprocess.run(
        [sys.executable, "scripts/validate_research_release.py", "--release", str(release), "--out", str(out)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    metrics = json.loads(out.read_text(encoding="utf-8"))
    assert metrics["required_artifact_rank_evidence_failures"] == 1
    assert metrics["status"] == "FAIL"


def test_research_release_validator_fails_when_required_artifact_liquidity_evidence_mismatches_monthly_scope(tmp_path):
    release = tmp_path / "release"
    _write_release(release, ["SEC1"])
    pq.write_table(
        pa.table(
            {
                "security_id": ["SEC1"],
                "enters_liquid_v1": [True],
                "enters_top750": [True],
                "first_research_date": ["2020-03-31"],
                "last_research_date": ["2020-03-31"],
                "research_identity_quality": ["RECONSTRUCTED_TRADING_IDENTITY"],
                "price_adjustment_quality": ["NO_ADJUSTMENT_REQUIRED"],
                "price_adjustment_ok": [True],
                "status_quality": ["OBSERVED_OFFICIAL_TRADE"],
                "active_trading_ok": [True],
                "instrument_type": ["ORDINARY_EQUITY"],
                "instrument_type_quality": ["OFFICIAL_REFERENCE"],
                "best_rank_126": [700],
                "worst_rank_126": [700],
                "max_median_traded_value_60": [9_000_000.0],
                "max_median_traded_value_126": [12_000_000.0],
                "max_positive_volume_days_60": [50],
            }
        ),
        release / "required_research_security.parquet",
    )
    out = tmp_path / "validation.json"

    result = subprocess.run(
        [sys.executable, "scripts/validate_research_release.py", "--release", str(release), "--out", str(out)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    metrics = json.loads(out.read_text(encoding="utf-8"))
    assert metrics["required_artifact_liquidity_evidence_failures"] == 1
    assert metrics["status"] == "FAIL"
