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
