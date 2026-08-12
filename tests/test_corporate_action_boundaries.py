from scripts.normalize_corporate_actions import (
    classify,
    composite_rights_price_factor,
    face_value_transition,
    has_unsupported_rights_component,
    selective_bonus_price_factor,
)
from scripts.validate_corporate_action_boundaries import cash_aware_holder_value_ratio, classify_boundary


def test_boundary_classification_preserves_missing_side_semantics():
    assert classify_boundary(None, 100.0, 2.0, 0.15) == (None, "NO_PRE_EVENT_OBSERVATION")
    assert classify_boundary(100.0, None, 2.0, 0.15) == (None, "NO_POST_EVENT_OBSERVATION")
    assert classify_boundary(None, None, 2.0, 0.15) == (None, "NO_BOUNDARY_OBSERVATIONS")


def test_boundary_classification_checks_holder_value_continuity():
    ratio, status = classify_boundary(100.0, 50.0, 2.0, 0.15)
    assert ratio == 1.0
    assert status == "PASS"

    ratio, status = classify_boundary(100.0, 58.0, 2.0, 0.15)
    assert ratio == 1.16
    assert status == "ADVISORY_BOUNDARY_DRIFT"

    ratio, status = classify_boundary(100.0, 70.0, 2.0, 0.15)
    assert ratio == 1.4
    assert status == "WARNING_LARGE_BOUNDARY_MOVE"

    ratio, status = classify_boundary(100.0, 50.0, 2.0, 0.15, pre_session_gap=12, post_session_gap=1)
    assert ratio == 1.0
    assert status == "NO_LOCAL_BOUNDARY_OBSERVATION"


def test_ex_date_boundary_uses_opening_price_semantics():
    ratio, status = classify_boundary(14363.85, 2961.0, 5.0, 0.15)
    assert round(ratio, 6) == 1.030713
    assert status == "PASS"


def test_preference_share_bonus_is_not_common_equity_bonus():
    assert classify("Bonus Preference Shares 21:1") == "BONUS_PREFERENCE_SECURITY"
    assert classify("Bonus Ncrps 1:116") == "BONUS_PREFERENCE_SECURITY"


def test_bonus_abbreviation_overrides_dividend_text():
    assert classify("Div-Rs.5.50 Pr Sh/Bon 5:1purpose Revised") == "BONUS"


def test_face_value_transition_accepts_plain_slash_notation():
    old_face, new_face, factor = face_value_transition(
        "Bonus 1:1 / Face Value Split From 10/- To Face Value 2/-", "BONUS"
    )
    assert (old_face, new_face, factor) == (10.0, 2.0, 0.2)


def test_face_value_transition_accepts_abbreviated_split_notation():
    old_face, new_face, factor = face_value_transition(
        "Bonus-1:1 Spl-Rs 5/ To 2/", "BONUS"
    )
    assert (old_face, new_face, factor) == (5.0, 2.0, 0.4)


def test_face_value_transition_accepts_fv_spl_abbreviation():
    old_face, new_face, factor = face_value_transition(
        "Fv Spl-10 To 5 / Bon 1:2", "BONUS"
    )
    assert (old_face, new_face, factor) == (10.0, 5.0, 0.5)


def test_bonus_rights_composite_requires_factor_review():
    subject = "Bonus 1:2/Rights 1:1"
    assert classify(subject) == "BONUS"
    assert has_unsupported_rights_component(subject, "BONUS") is True


def test_plain_bonus_does_not_require_rights_review():
    assert has_unsupported_rights_component("Bonus 1:2", "BONUS") is False


def test_lakshvilas_composite_rights_factor_is_cash_aware():
    factor = composite_rights_price_factor(163.60, bonus_ratio=0.5, rights_ratio=1.0, subscription_price=50.0)
    assert round(factor, 10) == 0.5222493888
    assert round(1.0 / factor, 6) != 2.5
    ratio = cash_aware_holder_value_ratio(163.60, 83.95, post_shares=2.5, cash_contribution=50.0)
    assert round(ratio, 3) == 0.977


def test_kwality_selective_bonus_uses_aggregate_dilution_not_nominal_ratio():
    factor = selective_bonus_price_factor(182000000, 203186434)
    assert round(factor, 10) == 0.8957290918
    assert round(factor, 10) != round(7 / 12, 10)


def test_large_move_boundary_remains_distinct_before_review_layer():
    ratio, status = classify_boundary(100.0, 130.0, 1.0, 0.15)
    assert ratio == 1.3
    assert status == "WARNING_LARGE_BOUNDARY_MOVE"
