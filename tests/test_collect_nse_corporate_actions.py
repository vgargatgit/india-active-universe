from __future__ import annotations

from datetime import date

import pytest

from scripts.collect_nse_corporate_actions import (
    CorporateActionRecoveryError,
    build_url,
    merge_rows,
    validate_payload,
)


def row(**overrides):
    value = {
        "symbol": "ABC",
        "series": "EQ",
        "subject": "BONUS 1:1",
        "exDate": "31-Jan-2020",
        "recDate": "31-Jan-2020",
        "isin": "INE000A01001",
    }
    value.update(overrides)
    return value


def test_build_url_uses_bounded_official_equity_api() -> None:
    url = build_url(date(2020, 1, 1), date(2020, 12, 31))
    assert url.startswith("https://www.nseindia.com/api/corporates-corporateActions?")
    assert "index=equities" in url
    assert "from_date=01-01-2020" in url
    assert "to_date=31-12-2020" in url


def test_validate_payload_requires_semantic_fields_and_event_date() -> None:
    assert validate_payload([row()], source_url="official") == [row()]
    with pytest.raises(CorporateActionRecoveryError, match="required fields"):
        validate_payload([row(symbol="")], source_url="official")
    with pytest.raises(CorporateActionRecoveryError, match="neither exDate nor recDate"):
        validate_payload([row(exDate=None, recDate=None)], source_url="official")
    with pytest.raises(CorporateActionRecoveryError, match="not a JSON list"):
        validate_payload({"data": [row()]}, source_url="official")


def test_merge_rows_is_deterministic_and_deduplicates_exact_source_rows() -> None:
    first = row(symbol="ZZZ", exDate="02-Feb-2020")
    second = row(symbol="AAA", exDate="01-Feb-2020")
    result = merge_rows([[first, second], [dict(first)]])
    assert result == [second, first]
    assert merge_rows([[second], [first]]) == result


def test_merge_preserves_distinct_source_corrections() -> None:
    original = row(subject="BONUS 1:1")
    corrected = row(subject="BONUS 2:1")
    assert len(merge_rows([[original, corrected]])) == 2
