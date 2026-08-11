from india_active_universe.profiles import (
    PRIORITY_SCOPE,
    PROFILE_ID,
    PROFILE_VERSION,
    RESEARCH_HIGH_CONFIDENCE_STATUS,
)
from scripts.build_research_reports import published_research_quality_bounds


def test_published_research_quality_bounds_uses_earliest_backed_rhc_interval():
    intervals = [
        {
            "start": "2013-01-01",
            "end": "2026-08-10",
            "status": RESEARCH_HIGH_CONFIDENCE_STATUS,
            "profile": PROFILE_ID,
            "profile_version": PROFILE_VERSION,
            "priority_scope": PRIORITY_SCOPE,
        },
        {
            "start": "2007-04-30",
            "end": "2012-12-31",
            "status": RESEARCH_HIGH_CONFIDENCE_STATUS,
            "profile": PROFILE_ID,
            "profile_version": PROFILE_VERSION,
            "priority_scope": PRIORITY_SCOPE,
        },
    ]

    assert published_research_quality_bounds(
        intervals,
        fallback_start="2006-01-31",
        fallback_end="2026-08-10",
    ) == ("2007-04-30", "2012-12-31")


def test_published_research_quality_bounds_ignores_unscoped_candidate_evidence():
    intervals = [
        {
            "start": "2007-04-30",
            "end": "2012-12-31",
            "status": "RESEARCH_EXPLORATORY",
            "profile": PROFILE_ID,
            "profile_version": PROFILE_VERSION,
            "priority_scope": PRIORITY_SCOPE,
        },
        {
            "start": "2008-01-31",
            "end": "2012-12-31",
            "status": RESEARCH_HIGH_CONFIDENCE_STATUS,
            "profile": PROFILE_ID,
            "profile_version": PROFILE_VERSION,
            "priority_scope": "ALL_SECURITIES",
        },
    ]

    assert published_research_quality_bounds(
        intervals,
        fallback_start="2006-01-31",
        fallback_end="2026-08-10",
    ) == ("2006-01-31", "2026-08-10")
