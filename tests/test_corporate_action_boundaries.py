from scripts.normalize_corporate_actions import classify, face_value_transition
from scripts.validate_corporate_action_boundaries import classify_boundary


def test_boundary_classification_preserves_missing_side_semantics():
    assert classify_boundary(None, 100.0, 2.0, 0.15) == (None, "NO_PRE_EVENT_OBSERVATION")
    assert classify_boundary(100.0, None, 2.0, 0.15) == (None, "NO_POST_EVENT_OBSERVATION")
    assert classify_boundary(None, None, 2.0, 0.15) == (None, "NO_BOUNDARY_OBSERVATIONS")


def test_boundary_classification_checks_holder_value_continuity():
    ratio, status = classify_boundary(100.0, 50.0, 2.0, 0.15)
    assert ratio == 1.0
    assert status == "PASS"

    ratio, status = classify_boundary(100.0, 70.0, 2.0, 0.15)
    assert ratio == 1.4
    assert status == "WARNING_LARGE_BOUNDARY_MOVE"

    ratio, status = classify_boundary(100.0, 50.0, 2.0, 0.15, pre_session_gap=12, post_session_gap=1)
    assert ratio == 1.0
    assert status == "NO_LOCAL_BOUNDARY_OBSERVATION"


def test_preference_share_bonus_is_not_common_equity_bonus():
    assert classify("Bonus Preference Shares 21:1") == "BONUS_PREFERENCE_SECURITY"
    assert classify("Bonus Ncrps 1:116") == "BONUS_PREFERENCE_SECURITY"


def test_face_value_transition_accepts_plain_slash_notation():
    old_face, new_face, factor = face_value_transition(
        "Bonus 1:1 / Face Value Split From 10/- To Face Value 2/-", "BONUS"
    )
    assert (old_face, new_face, factor) == (10.0, 2.0, 0.2)
