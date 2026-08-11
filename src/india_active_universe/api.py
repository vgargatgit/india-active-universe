from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Iterable

from .profiles import (
    CANDIDATE_AUDIT_STATUS_VALUES,
    CANDIDATE_ADVISORY_READINESS_KEYS,
    CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS,
    CANDIDATE_DECISION_GATE_KEYS,
    CANDIDATE_DECISION_GATE_VALUES,
    CANDIDATE_DECISION_REQUIRED_FIELDS,
    CANDIDATE_FAIL_VALUE,
    CANDIDATE_GATE_PASS_INTERPRETATION,
    CANDIDATE_HARD_FAILURE_KEYS,
    CANDIDATE_NOT_RECORDED_VALUE,
    CANDIDATE_NUMERIC_HARD_FAILURE_KEYS,
    CANDIDATE_PASS_VALUE,
    CANDIDATE_FEATURE_READINESS_POLICY,
    CANDIDATE_PIT_UNIVERSE_INTERVAL_TYPE,
    CANDIDATE_PROMOTION_API_METHODS,
    CANDIDATE_PROMOTION_INTERPRETATION_VALUES,
    CANDIDATE_PROMOTION_SUMMARY_FIELDS,
    CANDIDATE_REFINED_BOUNDARY_SCAN_METHOD,
    CANDIDATE_RESEARCH_START_DATES,
    DATA_RELEASE_MANIFEST_ARTIFACT,
    FEATURE_READINESS_WINDOWS,
    FEATURE_WARMUP_STATUS,
    LIQUID_V1_DEFINITION,
    PROFILE_ID,
    PROFILE_VERSION,
    RESEARCH_EXPLORATORY_STATUS,
    RESEARCH_HIGH_CONFIDENCE_STATUS,
    RESEARCH_RELEASE_MANIFEST_ARTIFACT,
    RESEARCH_START_DATE,
    SOURCE_ONLY_STATUS,
    TOP_LIQUIDITY_RANKING_METRIC,
)
from .storage import iter_jsonl, read_jsonl


def _as_date(value: str | date) -> date:
    return date.fromisoformat(value) if isinstance(value, str) else value


class CoverageError(ValueError):
    """The requested date is outside the trusted release coverage."""


def _normalize_candidate_promotion_decisions(rows: Any) -> list[dict[str, Any]]:
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise ValueError("candidate_promotion_decisions must be a list")
    decisions: list[dict[str, Any]] = []
    candidate_starts: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"candidate_promotion_decisions[{index}] must be an object")
        missing = [field for field in CANDIDATE_DECISION_REQUIRED_FIELDS if field not in row]
        if missing:
            raise ValueError(f"candidate_promotion_decisions[{index}] missing required fields: {missing}")
        candidate_start = _as_date(row["candidate_start"]).isoformat()
        if candidate_start not in CANDIDATE_RESEARCH_START_DATES:
            raise ValueError(f"candidate_promotion_decisions[{index}] candidate_start is not configured: {candidate_start}")
        audit_status = row["candidate_audit_status"]
        if audit_status not in CANDIDATE_AUDIT_STATUS_VALUES:
            raise ValueError(f"candidate_promotion_decisions[{index}].candidate_audit_status is invalid: {audit_status}")
        for field in CANDIDATE_DECISION_GATE_KEYS:
            gate_value = row[field]
            if gate_value not in CANDIDATE_DECISION_GATE_VALUES:
                raise ValueError(f"candidate_promotion_decisions[{index}].{field} is invalid: {gate_value}")
        for field in CANDIDATE_ADVISORY_READINESS_KEYS:
            gate_value = row[field]
            if gate_value not in CANDIDATE_DECISION_GATE_VALUES:
                raise ValueError(f"candidate_promotion_decisions[{index}].{field} is invalid: {gate_value}")
        feature_readiness = row["feature_readiness"]
        if not isinstance(feature_readiness, dict):
            raise ValueError(f"candidate_promotion_decisions[{index}].feature_readiness must be an object")
        if type(feature_readiness.get("feature_warmup_not_ready")) is not bool:
            raise ValueError(f"candidate_promotion_decisions[{index}].feature_readiness.feature_warmup_not_ready must be bool")
        if "feature_model_readiness_complete" in row and type(row["feature_model_readiness_complete"]) is not bool:
            raise ValueError(f"candidate_promotion_decisions[{index}].feature_model_readiness_complete must be bool")
        if "feature_model_readiness_complete" in row and row["feature_model_readiness_complete"] == feature_readiness["feature_warmup_not_ready"]:
            raise ValueError(
                f"candidate_promotion_decisions[{index}].feature_model_readiness_complete contradicts feature_readiness"
            )
        if "pit_universe_gate_pass" in row and type(row["pit_universe_gate_pass"]) is not bool:
            raise ValueError(f"candidate_promotion_decisions[{index}].pit_universe_gate_pass must be bool")
        if "pit_universe_gate_pass" in row and row["pit_universe_gate_pass"] != (audit_status == CANDIDATE_PASS_VALUE):
            raise ValueError(
                f"candidate_promotion_decisions[{index}].pit_universe_gate_pass contradicts candidate_audit_status"
            )
        promotion_interpretation = row["promotion_interpretation"]
        if promotion_interpretation not in CANDIDATE_PROMOTION_INTERPRETATION_VALUES:
            raise ValueError(
                f"candidate_promotion_decisions[{index}].promotion_interpretation is invalid: "
                f"{promotion_interpretation}"
            )
        hard_failures = row["hard_failures"]
        if not isinstance(hard_failures, dict):
            raise ValueError(f"candidate_promotion_decisions[{index}].hard_failures must be an object")
        missing_hard_failures = [field for field in CANDIDATE_HARD_FAILURE_KEYS if field not in hard_failures]
        if missing_hard_failures:
            raise ValueError(
                f"candidate_promotion_decisions[{index}].hard_failures missing required fields: "
                f"{missing_hard_failures}"
            )
        extra_hard_failures = [field for field in hard_failures if field not in CANDIDATE_HARD_FAILURE_KEYS]
        if extra_hard_failures:
            raise ValueError(
                f"candidate_promotion_decisions[{index}].hard_failures has unexpected fields: "
                f"{extra_hard_failures}"
            )
        for field in CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS:
            if type(hard_failures[field]) is not bool:
                raise ValueError(f"candidate_promotion_decisions[{index}].hard_failures.{field} must be bool")
        for field in CANDIDATE_NUMERIC_HARD_FAILURE_KEYS:
            if type(hard_failures[field]) is not int:
                raise ValueError(f"candidate_promotion_decisions[{index}].hard_failures.{field} must be int")
        active_hard_failures = [
            field for field in CANDIDATE_HARD_FAILURE_KEYS
            if hard_failures[field]
        ]
        if audit_status == CANDIDATE_PASS_VALUE and active_hard_failures:
            raise ValueError(
                f"candidate_promotion_decisions[{index}] is PASS with active hard failures: "
                f"{active_hard_failures}"
            )
        if audit_status == CANDIDATE_FAIL_VALUE and not active_hard_failures:
            raise ValueError(f"candidate_promotion_decisions[{index}] is FAIL without active hard failures")
        gate_failures = [
            field for field in CANDIDATE_DECISION_GATE_KEYS
            if row[field] != CANDIDATE_PASS_VALUE
        ]
        if promotion_interpretation == CANDIDATE_GATE_PASS_INTERPRETATION:
            if audit_status != CANDIDATE_PASS_VALUE or gate_failures:
                raise ValueError(
                    f"candidate_promotion_decisions[{index}] has gate-pass interpretation without "
                    f"PASS audit status and all PASS gates"
                )
        if audit_status == CANDIDATE_PASS_VALUE and not gate_failures and promotion_interpretation != CANDIDATE_GATE_PASS_INTERPRETATION:
            raise ValueError(
                f"candidate_promotion_decisions[{index}] is gate-pass but has non-gate-pass interpretation: "
                f"{promotion_interpretation}"
            )
        if candidate_start in candidate_starts:
            raise ValueError(f"candidate_promotion_decisions duplicate candidate_start: {candidate_start}")
        candidate_starts.add(candidate_start)
        decisions.append({**row, "candidate_start": candidate_start})
    missing_candidate_starts = [
        candidate_start for candidate_start in CANDIDATE_RESEARCH_START_DATES
        if candidate_start not in candidate_starts
    ]
    if decisions and missing_candidate_starts:
        raise ValueError(f"candidate_promotion_decisions missing configured candidate starts: {missing_candidate_starts}")
    candidate_start_order = {
        candidate_start: index
        for index, candidate_start in enumerate(CANDIDATE_RESEARCH_START_DATES)
    }
    return sorted(decisions, key=lambda row: candidate_start_order[row["candidate_start"]])


def _normalize_earliest_candidate_gate_pass_start(value: Any, decisions: list[dict[str, Any]]) -> date | None:
    gate_pass_starts = sorted(
        row["candidate_start"]
        for row in decisions
        if row["candidate_audit_status"] == CANDIDATE_PASS_VALUE
        and all(row[field] == CANDIDATE_PASS_VALUE for field in CANDIDATE_DECISION_GATE_KEYS)
        and row["promotion_interpretation"] == CANDIDATE_GATE_PASS_INTERPRETATION
    )
    if value is None:
        if gate_pass_starts:
            raise ValueError("earliest_candidate_gate_pass_start is null despite gate-pass candidate decisions")
        return None
    point = _as_date(value).isoformat()
    if point not in CANDIDATE_RESEARCH_START_DATES:
        raise ValueError(f"earliest_candidate_gate_pass_start is not configured: {point}")
    if not gate_pass_starts:
        raise ValueError("earliest_candidate_gate_pass_start is set without gate-pass candidate decisions")
    if point != gate_pass_starts[0]:
        raise ValueError(
            f"earliest_candidate_gate_pass_start must be earliest gate-pass candidate: "
            f"{gate_pass_starts[0]}"
        )
    return _as_date(point)


def _normalize_refined_earliest_candidate_gate_pass_boundary(value: Any, decisions: list[dict[str, Any]]) -> date | None:
    refined_boundaries = sorted(
        _as_date(row["refined_earliest_passing_snapshot"]).isoformat()
        for row in decisions
        if row.get("refined_earliest_passing_snapshot")
    )
    if value is None:
        if refined_boundaries:
            raise ValueError("refined_earliest_candidate_gate_pass_boundary is null despite refined gate-pass candidate boundaries")
        return None
    point = _as_date(value).isoformat()
    if not refined_boundaries:
        raise ValueError("refined_earliest_candidate_gate_pass_boundary is set without refined gate-pass candidate boundaries")
    if point != refined_boundaries[0]:
        raise ValueError(
            "refined_earliest_candidate_gate_pass_boundary must be earliest refined gate-pass boundary: "
            f"{refined_boundaries[0]}"
        )
    return _as_date(point)


def _validate_candidate_interval_recommendations(
    manifest_name: str,
    manifest: dict[str, Any],
    refined_boundary: date | None,
    *,
    required: bool,
) -> None:
    expected_status = "CANDIDATE_REFINED_BOUNDARY_AVAILABLE" if refined_boundary else "NO_REFINED_BOUNDARY"
    expected_start = refined_boundary.isoformat() if refined_boundary else None

    def validate_common(field: str, interval: Any) -> dict[str, Any]:
        if not isinstance(interval, dict):
            raise ValueError(f"{manifest_name} {field} is missing or not an object")
        if interval.get("status") != expected_status:
            raise ValueError(f"{manifest_name} {field}.status does not match refined boundary availability")
        if interval.get("start") != expected_start:
            raise ValueError(f"{manifest_name} {field}.start does not match refined boundary")
        if not isinstance(interval.get("end"), str):
            raise ValueError(f"{manifest_name} {field}.end is missing or not a string")
        if interval.get("profile") != PROFILE_ID:
            raise ValueError(f"{manifest_name} {field}.profile is not the published profile")
        if interval.get("profile_version") != PROFILE_VERSION:
            raise ValueError(f"{manifest_name} {field}.profile_version is not the published profile version")
        if interval.get("boundary_scan_method") != CANDIDATE_REFINED_BOUNDARY_SCAN_METHOD:
            raise ValueError(f"{manifest_name} {field}.boundary_scan_method is not the published refined scan method")
        if interval.get("promotion_status") != "NOT_PROMOTED_UNLESS_PRESENT_IN_RESEARCH_QUALITY_INTERVALS":
            raise ValueError(f"{manifest_name} {field}.promotion_status is not fail-closed")
        return interval

    recommendation_fields_present = (
        "candidate_recommended_research_interval" in manifest
        or "candidate_recommended_pit_universe_interval" in manifest
    )
    if not required and not recommendation_fields_present:
        return
    validate_common(
        "candidate_recommended_research_interval",
        manifest.get("candidate_recommended_research_interval"),
    )
    pit_interval = validate_common(
        "candidate_recommended_pit_universe_interval",
        manifest.get("candidate_recommended_pit_universe_interval"),
    )
    if pit_interval.get("interval_type") != CANDIDATE_PIT_UNIVERSE_INTERVAL_TYPE:
        raise ValueError(f"{manifest_name} candidate_recommended_pit_universe_interval.interval_type is not PIT_UNIVERSE")
    if pit_interval.get("feature_readiness_policy") != CANDIDATE_FEATURE_READINESS_POLICY:
        raise ValueError(
            f"{manifest_name} candidate_recommended_pit_universe_interval.feature_readiness_policy does not separate feature readiness"
        )


def _validate_research_quality_intervals_after_warmup(
    manifest_name: str,
    intervals: Any,
    warmup_coverage: dict[str, Any],
    refined_boundary: date | None,
) -> None:
    if not isinstance(intervals, list):
        return
    earliest_fully_warmed = warmup_coverage.get("earliest_fully_warmed_date")
    for interval in intervals:
        if (
            isinstance(interval, dict)
            and interval.get("status") == RESEARCH_HIGH_CONFIDENCE_STATUS
            and interval.get("start")
            and _as_date(interval["start"]) < _as_date(RESEARCH_START_DATE)
            and (not earliest_fully_warmed or _as_date(interval["start"]) < _as_date(earliest_fully_warmed))
        ):
            raise ValueError(
                f"{manifest_name} pre-2013 RESEARCH_HIGH_CONFIDENCE interval starts before earliest fully warmed date"
            )
        if (
            isinstance(interval, dict)
            and interval.get("status") == RESEARCH_HIGH_CONFIDENCE_STATUS
            and interval.get("start")
            and _as_date(interval["start"]) < _as_date(RESEARCH_START_DATE)
            and (refined_boundary is None or _as_date(interval["start"]) < refined_boundary)
        ):
            raise ValueError(
                f"{manifest_name} pre-2013 RESEARCH_HIGH_CONFIDENCE interval starts before refined candidate gate-pass boundary"
            )


def _validate_research_quality_scalar_matches_interval(
    manifest_name: str,
    research_quality: dict[str, Any],
    intervals: Any,
) -> None:
    if research_quality.get("status") != RESEARCH_HIGH_CONFIDENCE_STATUS or not research_quality.get("start"):
        return
    if not isinstance(intervals, list) or not any(
        isinstance(interval, dict)
        and interval.get("status") == RESEARCH_HIGH_CONFIDENCE_STATUS
        and interval.get("start") == research_quality.get("start")
        for interval in intervals
    ):
        raise ValueError(f"{manifest_name} research_quality.start is not backed by a matching RESEARCH_HIGH_CONFIDENCE interval")


class SecurityMaster:
    """Date-sensitive identity lookup over a published security master."""

    def __init__(self, rows: Iterable[dict[str, Any]] = ()) -> None:
        self.rows = [_normalize_dates(row) for row in rows]

    def resolve_symbol(self, symbol: str, as_of_date: str | date, exchange: str = "NSE", series: str = "EQ") -> dict[str, Any]:
        point = _as_date(as_of_date)
        matches = [row for row in self.rows if row.get("exchange") == exchange and row.get("series") == series and row.get("symbol") == symbol and row["effective_from"] <= point and (row.get("effective_to") is None or point <= row["effective_to"])]
        if len(matches) != 1:
            raise LookupError(f"Expected one identity for {exchange}:{symbol}:{series} on {point}, found {len(matches)}")
        return matches[0]


class EffectiveHistoryStore:
    """Lookup for an effective-dated history keyed by an entity ID."""

    def __init__(self, rows: Iterable[dict[str, Any]] = (), *, id_field: str) -> None:
        self.id_field = id_field
        self.rows = [_normalize_dates(row) for row in rows]

    def history(self, entity_id: str, start: str | date, end: str | date) -> list[dict[str, Any]]:
        begin, finish = _as_date(start), _as_date(end)
        return sorted(
            (row for row in self.rows if row.get(self.id_field) == entity_id and row.get("effective_from") <= finish and (row.get("effective_to") is None or row["effective_to"] >= begin)),
            key=lambda row: row["effective_from"],
        )

    def at(self, entity_id: str, as_of_date: str | date) -> dict[str, Any]:
        point = _as_date(as_of_date)
        matches = [
            row for row in self.rows
            if row.get(self.id_field) == entity_id
            and row.get("effective_from") <= point
            and (row.get("effective_to") is None or point <= row["effective_to"])
        ]
        if len(matches) != 1:
            raise LookupError(f"Expected one history row for {entity_id} on {point}, found {len(matches)}")
        return matches[0]


class CompanyNameHistoryStore(EffectiveHistoryStore):
    def __init__(self, rows: Iterable[dict[str, Any]] = ()) -> None:
        super().__init__(rows, id_field="issuer_id")

    def name_at(self, issuer_id: str, as_of_date: str | date) -> str:
        return self.at(issuer_id, as_of_date)["company_name"]


class IsinHistoryStore(EffectiveHistoryStore):
    def __init__(self, rows: Iterable[dict[str, Any]] = ()) -> None:
        super().__init__(rows, id_field="security_id")

    def isin_at(self, security_id: str, as_of_date: str | date) -> str | None:
        return self.at(security_id, as_of_date).get("isin")


class ParquetEffectiveHistoryStore(EffectiveHistoryStore):
    def __init__(self, path: str | Path, *, id_field: str) -> None:
        import pyarrow.parquet as parquet
        self.path = Path(path)
        super().__init__(parquet.read_table(self.path).to_pylist(), id_field=id_field)


class ParquetCompanyNameHistoryStore(CompanyNameHistoryStore):
    def __init__(self, path: str | Path) -> None:
        import pyarrow.parquet as parquet
        self.path = Path(path)
        super().__init__(parquet.read_table(self.path).to_pylist())


class ParquetIsinHistoryStore(IsinHistoryStore):
    def __init__(self, path: str | Path) -> None:
        import pyarrow.parquet as parquet
        self.path = Path(path)
        super().__init__(parquet.read_table(self.path).to_pylist())


class PriceStore:
    def __init__(self, rows: Iterable[dict[str, Any]] = ()) -> None:
        self.rows = [_normalize_dates(row) for row in rows]

    def history(self, security_id: str, start: str | date, end: str | date) -> list[dict[str, Any]]:
        begin, finish = _as_date(start), _as_date(end)
        return sorted((row for row in self.rows if row.get("security_id") == security_id and begin <= row["date"] <= finish), key=lambda row: row["date"])


class FilePriceStore(PriceStore):
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.rows = []

    def history(self, security_id: str, start: str | date, end: str | date) -> list[dict[str, Any]]:
        begin, finish = _as_date(start), _as_date(end)
        return sorted((_normalize_dates(row) for row in iter_jsonl(self.path) if row.get("security_id") == security_id and begin <= _as_date(row["date"]) <= finish), key=lambda row: row["date"])


class ParquetPriceStore(PriceStore):
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.rows = []

    def history(self, security_id: str, start: str | date, end: str | date) -> list[dict[str, Any]]:
        import pyarrow.parquet as parquet
        begin, finish = _as_date(start).isoformat(), _as_date(end).isoformat()
        table = parquet.read_table(self.path, filters=[("security_id", "=", security_id), ("date", ">=", begin), ("date", "<=", finish)])
        return sorted(table.to_pylist(), key=lambda row: row["date"])


class UniverseStore:
    def __init__(self, rows: Iterable[dict[str, Any]] = ()) -> None:
        self.rows = [_normalize_dates(row) for row in rows]

    def active_on(self, as_of_date: str | date) -> list[dict[str, Any]]:
        point = _as_date(as_of_date)
        return [row for row in self.rows if row.get("date") == point and row.get("active") is True]

    def _positive_volume_days_60(self, row: dict[str, Any]) -> int:
        if row.get("positive_volume_days_60") is not None:
            return row["positive_volume_days_60"]
        sessions = min(row.get("history_sessions", 0), 60)
        return max(0, sessions - (row.get("zero_volume_days_60") or 0))

    def _liquid_v1_eligible(self, row: dict[str, Any]) -> bool:
        if row.get("NSE_BROAD_LIQUID_PIT_V1_eligible") is not None:
            return row["NSE_BROAD_LIQUID_PIT_V1_eligible"] is True
        price = row.get("price", row.get("close"))
        listing_age = row.get("listing_age_sessions", row.get("history_sessions", 0))
        return (
            row.get("active") is LIQUID_V1_DEFINITION["active"]
            and row.get("instrument_type") == LIQUID_V1_DEFINITION["instrument_type"]
            and row.get("trading_status") == LIQUID_V1_DEFINITION["trading_status"]
            and row.get("research_identity_ok") is True
            and row.get("price_adjustment_ok") is True
            and price is not None and price >= LIQUID_V1_DEFINITION["price_min"]
            and listing_age >= LIQUID_V1_DEFINITION["listing_age_sessions_min"]
            and self._positive_volume_days_60(row) >= LIQUID_V1_DEFINITION["positive_volume_days_60_min"]
            and row.get("median_traded_value_60", 0) >= LIQUID_V1_DEFINITION["median_traded_value_60_min"]
        )

    def eligible_on(self, as_of_date: str | date, *, min_price: float | None = None, min_history_sessions: int = 0, min_positive_volume_days_60: int | None = None, min_median_traded_value_60: float | None = None) -> list[dict[str, Any]]:
        rows = self.active_on(as_of_date)
        return [row for row in rows if (min_price is None or (row.get("close") is not None and row["close"] >= min_price)) and row.get("history_sessions", 0) >= min_history_sessions and (min_positive_volume_days_60 is None or self._positive_volume_days_60(row) >= min_positive_volume_days_60) and (min_median_traded_value_60 is None or row.get("median_traded_value_60", 0) >= min_median_traded_value_60)]

    def ranked_liquid_on(self, as_of_date: str | date, n: int, *, metric: str = TOP_LIQUIDITY_RANKING_METRIC) -> list[dict[str, Any]]:
        rows = [
            row for row in self.active_on(as_of_date)
            if row.get(metric) is not None
            and row.get("instrument_type") == LIQUID_V1_DEFINITION["instrument_type"]
            and row.get("trading_status") == LIQUID_V1_DEFINITION["trading_status"]
        ]
        return sorted(rows, key=lambda row: row[metric], reverse=True)[:n]

    def profile_on(self, as_of_date: str | date, profile: str = PROFILE_VERSION) -> list[dict[str, Any]]:
        point = _as_date(as_of_date)
        if profile != PROFILE_VERSION:
            raise ValueError(f"Unknown universe profile: {profile}")
        rows = [row for row in self.rows if row.get("date") == point and self._liquid_v1_eligible(row)]
        for row in rows:
            row.setdefault("profile_id", PROFILE_ID)
            row.setdefault("profile_version", profile)
            row.setdefault("as_of_date", point)
            row.setdefault("eligibility_result", "ELIGIBLE")
            row.setdefault("eligibility_reason_codes", f"PASSED_{PROFILE_VERSION}")
        return rows


class FileUniverseStore(UniverseStore):
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.rows = []

    def active_on(self, as_of_date: str | date) -> list[dict[str, Any]]:
        point = _as_date(as_of_date)
        return [_normalize_dates(row) for row in iter_jsonl(self.path) if row.get("date") == point.isoformat() and row.get("active") is True]

    def eligible_on(self, as_of_date: str | date, **kwargs: Any) -> list[dict[str, Any]]:
        return UniverseStore.eligible_on(self, as_of_date, **kwargs)


class ParquetUniverseStore(UniverseStore):
    def __init__(self, path: str | Path, features_path: str | Path | None = None) -> None:
        self.path = Path(path)
        self.features_path = Path(features_path) if features_path else None
        self.rows = []

    def active_on(self, as_of_date: str | date) -> list[dict[str, Any]]:
        point = _as_date(as_of_date).isoformat()
        import pyarrow.parquet as parquet
        output = parquet.read_table(self.path, filters=[("date", "=", point), ("active", "=", True)]).to_pylist()
        if self.features_path and self.features_path.exists() and output:
            feature_rows = parquet.read_table(self.features_path, filters=[("date", "=", point)]).to_pylist()
            by_security = {row["security_id"]: row for row in feature_rows}
            for row in output:
                feature = by_security.get(row["security_id"], {})
                for key in ("history_sessions", "observed_history_sessions", "listing_age_sessions", "listing_age_calendar_days", "price", "series", "listing_status", "valid_trade_days_20", "valid_trade_days_60", "valid_trade_days_126", "valid_trade_days_252", "positive_volume_days_20", "positive_volume_days_60", "positive_volume_days_126", "positive_volume_days_252", "zero_volume_days_20", "zero_volume_days_60", "zero_volume_days_126", "zero_volume_days_252", "absent_observation_days_20", "absent_observation_days_60", "absent_observation_days_126", "absent_observation_days_252", "median_traded_value_20", "median_traded_value_60", "median_traded_value_126", "median_traded_value_252", "average_traded_value_20", "average_traded_value_60", "average_traded_value_126", "average_traded_value_252", "stale_price_days_60", "liquidity_percentile_126", "liquidity_bucket_126", "liquidity_rank_126", "liquidity_window_definition", "feature_as_of_date"):
                    if key in feature:
                        row[key] = feature[key]
        return output

    def ranked_liquid_on(self, as_of_date: str | date, n: int, *, metric: str = TOP_LIQUIDITY_RANKING_METRIC) -> list[dict[str, Any]]:
        rows = [
            row for row in self.active_on(as_of_date)
            if row.get(metric) is not None
            and row.get("instrument_type") == LIQUID_V1_DEFINITION["instrument_type"]
            and row.get("trading_status") == LIQUID_V1_DEFINITION["trading_status"]
        ]
        return sorted(rows, key=lambda row: row[metric], reverse=True)[:n]

    def profile_on(self, as_of_date: str | date, profile: str = PROFILE_VERSION) -> list[dict[str, Any]]:
        if profile != PROFILE_VERSION:
            raise ValueError(f"Unknown universe profile: {profile}")
        point = _as_date(as_of_date)
        import pyarrow.parquet as parquet
        rows = []
        date_rows = []
        for point_value in (point, point.isoformat()):
            try:
                rows = parquet.read_table(self.path, filters=[("date", "=", point_value), ("NSE_BROAD_LIQUID_PIT_V1_eligible", "=", True)]).to_pylist()
                date_rows = date_rows or rows
                if rows:
                    break
            except Exception:
                try:
                    date_rows = parquet.read_table(self.path, filters=[("date", "=", point_value)]).to_pylist()
                    rows = [row for row in date_rows if self._liquid_v1_eligible(row)]
                    if rows:
                        break
                except Exception:
                    continue
        for row in rows:
            row.setdefault("profile_id", PROFILE_ID)
            row.setdefault("profile_version", profile)
            row.setdefault("as_of_date", point)
            row.setdefault("eligibility_result", "ELIGIBLE")
            row.setdefault("eligibility_reason_codes", f"PASSED_{PROFILE_VERSION}")
        return rows


class StatusStore:
    """Effective-dated listing, trading, suspension, and terminal status."""

    def __init__(self, rows: Iterable[dict[str, Any]] = ()) -> None:
        self.rows = [_normalize_dates(row) for row in rows]

    def status_on(self, as_of_date: str | date) -> list[dict[str, Any]]:
        point = _as_date(as_of_date)
        return [
            row for row in self.rows
            if row.get("status_start") <= point
            and (row.get("status_end") is None or point <= row["status_end"])
        ]


class ParquetStatusStore(StatusStore):
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        super().__init__()

    def status_on(self, as_of_date: str | date) -> list[dict[str, Any]]:
        import pyarrow.parquet as parquet
        point = _as_date(as_of_date).isoformat()
        rows = parquet.read_table(self.path).to_pylist()
        return [
            row for row in rows
            if row.get("status_start") <= point
            and (row.get("status_end") is None or point <= row["status_end"])
        ]


class TerminalEventStore:
    """Terminal events and explicit downstream recovery scenarios."""

    def __init__(self, rows: Iterable[dict[str, Any]] = ()) -> None:
        self.rows = list(rows)

    def recovery_scenarios(self, security_id: str, *, last_observed_price: float | None = None) -> list[dict[str, Any]]:
        output = []
        for event in (row for row in self.rows if row.get("security_id") == security_id):
            common = {"security_id": security_id, "event_id": event.get("event_id"), "terminal_event_type": event.get("terminal_event_type")}
            output.append({**common, "scenario": "ZERO_RECOVERY", "value": 0.0, "value_basis": "DOWNSTREAM_ASSUMPTION", "canonical": False})
            output.append({**common, "scenario": "LAST_OBSERVED_PRICE", "value": last_observed_price, "value_basis": "LAST_OBSERVED_RAW_CLOSE", "canonical": False})
            if event.get("terminal_value") is not None:
                output.append({**common, "scenario": "DOCUMENTED_VALUE", "value": event["terminal_value"], "value_basis": event.get("terminal_value_basis"), "canonical": True})
        return output

    def resolution_queue_for_holdings(self, security_ids: Iterable[str]) -> list[dict[str, Any]]:
        held = set(security_ids)
        return [row for row in self.rows if row.get("security_id") in held]


class CalendarStore:
    """Official market sessions; no synthetic weekday generation."""

    def __init__(self, rows: Iterable[dict[str, Any]] = ()) -> None:
        self.rows = [_normalize_dates(row) for row in rows]

    def sessions_between(self, start: str | date, end: str | date) -> list[dict[str, Any]]:
        begin, finish = _as_date(start), _as_date(end)
        return sorted((row for row in self.rows if begin <= row["date"] <= finish), key=lambda row: row["date"])


class ParquetCalendarStore(CalendarStore):
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        super().__init__()

    def sessions_between(self, start: str | date, end: str | date) -> list[dict[str, Any]]:
        import pyarrow.parquet as parquet
        begin, finish = _as_date(start).isoformat(), _as_date(end).isoformat()
        return parquet.read_table(self.path, filters=[("date", ">=", begin), ("date", "<=", finish)]).to_pylist()


class DataPlatform:
    def __init__(self, root: str | Path = ".", *, strict: bool = False) -> None:
        self.root = Path(root)
        self.strict = strict
        self.coverage_start: date | None = None
        self.coverage_end: date | None = None
        self.verified_start: date | None = None
        self.verified_end: date | None = None
        self.quality_tier: str | None = None
        self.warmup_coverage: dict[str, Any] = {}
        self.research_quality_intervals: list[dict[str, Any]] = []
        self.candidate_promotion_decisions: list[dict[str, Any]] = []
        self.earliest_candidate_gate_pass_start: date | None = None
        self._refined_earliest_candidate_gate_pass_boundary: date | None = None
        self.security_master = SecurityMaster()
        self.company_names = CompanyNameHistoryStore()
        self.isins = IsinHistoryStore()
        self.prices = PriceStore()
        self.adjusted_prices = PriceStore()
        self.universe = UniverseStore()
        self.research_universe = UniverseStore()
        self.status = StatusStore()
        self.terminal_events = TerminalEventStore()
        self.calendar = CalendarStore()

    def _check_date(self, value: str | date) -> date:
        point = _as_date(value)
        start = self.verified_start or self.coverage_start
        end = self.verified_end or self.coverage_end
        if self.strict and ((start and point < start) or (end and point > end)):
            raise CoverageError(f"Date {point} is outside trusted release coverage {start} through {end}")
        return point

    def active_on(self, as_of_date: str | date) -> list[dict[str, Any]]:
        return self.universe.active_on(self._check_date(as_of_date))

    def eligible_on(self, as_of_date: str | date, **kwargs: Any) -> list[dict[str, Any]]:
        return self.universe.eligible_on(self._check_date(as_of_date), **kwargs)

    def ranked_liquid_on(self, as_of_date: str | date, n: int, **kwargs: Any) -> list[dict[str, Any]]:
        return self.universe.ranked_liquid_on(self._check_date(as_of_date), n, **kwargs)

    def profile_on(self, as_of_date: str | date, profile: str = PROFILE_VERSION) -> list[dict[str, Any]]:
        return self.research_universe.profile_on(self._check_date(as_of_date), profile)

    def status_on(self, as_of_date: str | date) -> list[dict[str, Any]]:
        return self.status.status_on(self._check_date(as_of_date))

    def observation_status(self, security_id: str, as_of_date: str | date) -> str:
        """Return explicit availability semantics for one security and date."""
        point = self._check_date(as_of_date)
        if not self.calendar.sessions_between(point, point):
            return "NO_MARKET_SESSION"
        identity = [
            row for row in self.security_master.rows
            if row.get("security_id") == security_id
            and row.get("effective_from") <= point
            and (row.get("effective_to") is None or point <= row["effective_to"])
        ]
        if not identity:
            return "SECURITY_NOT_LISTED"
        statuses = [row.get("trading_status") for row in self.status.status_on(point) if row.get("security_id") == security_id]
        if "SUSPENDED" in statuses:
            return "SECURITY_SUSPENDED"
        if "DELISTED" in statuses:
            return "SECURITY_NOT_LISTED"
        rows = self.prices.history(security_id, point, point)
        if rows:
            volume = rows[0].get("volume")
            return "NO_TRADE" if volume is None or volume <= 0 else "TRADED"
        return "UNKNOWN"

    def company_name_at(self, issuer_id: str, as_of_date: str | date) -> str:
        return self.company_names.name_at(issuer_id, self._check_date(as_of_date))

    def isin_at(self, security_id: str, as_of_date: str | date) -> str | None:
        return self.isins.isin_at(security_id, self._check_date(as_of_date))

    def history(self, security_id: str, start: str | date, end: str | date) -> list[dict[str, Any]]:
        begin, finish = self._check_date(start), self._check_date(end)
        return self.prices.history(security_id, begin, finish)

    def adjusted_history(self, security_id: str, start: str | date, end: str | date, *, series: str = "PRICE_RETURN") -> list[dict[str, Any]]:
        if series not in {"PRICE_RETURN", "TOTAL_RETURN"}:
            raise ValueError(f"Unknown adjusted-price series: {series}")
        begin, finish = self._check_date(start), self._check_date(end)
        rows = self.adjusted_prices.history(security_id, begin, finish)
        value_field = "price_return_adjusted_close" if series == "PRICE_RETURN" else "total_return_adjusted_close"
        fallback_value_field = "research_adjusted_close" if series == "PRICE_RETURN" else "research_adjusted_close_total_return"
        quality_field = "adjustment_quality" if series == "PRICE_RETURN" else "total_return_quality"
        return [{**row, "adjusted_close": row.get(value_field, row.get(fallback_value_field)), "adjusted_series": series, "adjusted_quality": row.get(quality_field)} for row in rows]

    def terminal_recovery_scenarios(self, security_id: str) -> list[dict[str, Any]]:
        last_price = None
        if self.coverage_start and self.coverage_end:
            history = self.prices.history(security_id, self.coverage_start, self.coverage_end)
            if history:
                last_price = history[-1].get("raw_close", history[-1].get("close"))
        return self.terminal_events.recovery_scenarios(security_id, last_observed_price=last_price)

    def terminal_event_resolution_queue_for_holdings(self, security_ids: Iterable[str]) -> list[dict[str, Any]]:
        return self.terminal_events.resolution_queue_for_holdings(security_ids)

    def sessions_between(self, start: str | date, end: str | date) -> list[dict[str, Any]]:
        begin, finish = self._check_date(start), self._check_date(end)
        return self.calendar.sessions_between(begin, finish)

    def research_quality_on(self, as_of_date: str | date) -> str:
        point = _as_date(as_of_date)
        for interval in self.research_quality_intervals:
            start = _as_date(interval["start"]) if interval.get("start") else None
            end = _as_date(interval["end"]) if interval.get("end") else None
            if (start is None or start <= point) and (end is None or point <= end):
                return interval.get("status", RESEARCH_EXPLORATORY_STATUS)
        if self.coverage_start and point < self.coverage_start:
            raise CoverageError(f"Date {point} is before observed source coverage {self.coverage_start}")
        if self.coverage_end and point > self.coverage_end:
            raise CoverageError(f"Date {point} is after observed source coverage {self.coverage_end}")
        fully_warmed = self.warmup_coverage.get("earliest_fully_warmed_date")
        if fully_warmed and point < _as_date(fully_warmed):
            return FEATURE_WARMUP_STATUS
        if self.coverage_start and self.coverage_end and self.coverage_start <= point <= self.coverage_end:
            return RESEARCH_EXPLORATORY_STATUS
        return SOURCE_ONLY_STATUS

    def feature_readiness(self, as_of_date: str | date) -> dict[str, Any]:
        point = _as_date(as_of_date)
        sessions = self.calendar.sessions_between(self.coverage_start or point, point)
        prior_sessions = sum(1 for row in sessions if row.get("date") < point)
        ready = {name: prior_sessions >= sessions_required for name, sessions_required in FEATURE_READINESS_WINDOWS.items()}
        return {
            "date": point,
            "prior_official_sessions": prior_sessions,
            "feature_readiness_windows": FEATURE_READINESS_WINDOWS,
            "ready": ready,
            "all_ready": all(ready.values()) if ready else False,
            "source": "OFFICIAL_NSE_TRADING_CALENDAR",
        }

    def earliest_feature_ready_date(self, feature_name: str) -> date | None:
        """Return the manifest-recorded earliest date for one feature-readiness window."""
        if feature_name not in FEATURE_READINESS_WINDOWS:
            raise ValueError(f"Unknown feature readiness window: {feature_name}")
        value = (self.warmup_coverage.get("feature_ready_dates") or {}).get(feature_name)
        return _as_date(value) if value else None

    def earliest_fully_warmed_date(self) -> date | None:
        """Return the manifest-recorded earliest date with all published readiness windows."""
        value = self.warmup_coverage.get("earliest_fully_warmed_date")
        return _as_date(value) if value else None

    def candidate_promotion_status(self) -> list[dict[str, Any]]:
        """Return configured early-history candidate-start promotion decisions."""
        return [dict(row) for row in self.candidate_promotion_decisions]

    def candidate_promotion_summary(self) -> dict[str, Any]:
        """Return the release-level early-history candidate promotion summary."""
        gate_pass_start_dates = [
            value.isoformat()
            for value in self.candidate_gate_pass_start_dates()
        ]
        recorded_earliest = (
            self.earliest_candidate_gate_pass_start.isoformat()
            if self.earliest_candidate_gate_pass_start
            else None
        )
        derived_earliest = gate_pass_start_dates[0] if gate_pass_start_dates else None
        refined_boundaries = sorted(
            str(row["refined_earliest_passing_snapshot"])
            for row in self.candidate_promotion_decisions
            if row.get("refined_earliest_passing_snapshot")
        )
        recorded_refined = (
            self._refined_earliest_candidate_gate_pass_boundary.isoformat()
            if self._refined_earliest_candidate_gate_pass_boundary
            else None
        )
        derived_refined = refined_boundaries[0] if refined_boundaries else None
        candidate_recommended_research_interval = {
            "status": "CANDIDATE_REFINED_BOUNDARY_AVAILABLE" if derived_refined else "NO_REFINED_BOUNDARY",
            "start": derived_refined,
            "end": self.coverage_end.isoformat() if self.coverage_end else None,
            "profile": PROFILE_ID,
            "profile_version": PROFILE_VERSION,
            "boundary_scan_method": CANDIDATE_REFINED_BOUNDARY_SCAN_METHOD,
            "promotion_status": "NOT_PROMOTED_UNLESS_PRESENT_IN_RESEARCH_QUALITY_INTERVALS",
        }
        candidate_recommended_pit_universe_interval = {
            **candidate_recommended_research_interval,
            "interval_type": CANDIDATE_PIT_UNIVERSE_INTERVAL_TYPE,
            "feature_readiness_policy": CANDIDATE_FEATURE_READINESS_POLICY,
        }
        return {
            "recorded_earliest_candidate_gate_pass_start": recorded_earliest,
            "earliest_candidate_gate_pass_start": derived_earliest,
            "recorded_matches_derived_earliest_candidate_gate_pass_start": recorded_earliest == derived_earliest,
            "candidate_gate_pass_start_dates": gate_pass_start_dates,
            "candidate_research_ready_start_dates": [
                value.isoformat()
                for value in self.candidate_research_ready_start_dates()
            ],
            "recorded_refined_earliest_candidate_gate_pass_boundary": recorded_refined,
            "refined_earliest_candidate_gate_pass_boundary": derived_refined,
            "recorded_matches_derived_refined_earliest_candidate_gate_pass_boundary": recorded_refined == derived_refined,
            "candidate_recommended_pit_universe_interval": candidate_recommended_pit_universe_interval,
            "candidate_recommended_research_interval": candidate_recommended_research_interval,
            "candidate_promotion_decisions": self.candidate_promotion_status(),
        }

    def candidate_promotion_contract(self) -> dict[str, Any]:
        """Return the machine-readable early-history candidate promotion schema."""
        return {
            "candidate_research_start_dates": CANDIDATE_RESEARCH_START_DATES,
            "candidate_promotion_api_methods": CANDIDATE_PROMOTION_API_METHODS,
            "candidate_decision_required_fields": CANDIDATE_DECISION_REQUIRED_FIELDS,
            "candidate_promotion_summary_fields": CANDIDATE_PROMOTION_SUMMARY_FIELDS,
            "candidate_decision_gate_keys": CANDIDATE_DECISION_GATE_KEYS,
            "candidate_advisory_readiness_keys": CANDIDATE_ADVISORY_READINESS_KEYS,
            "candidate_hard_failure_keys": CANDIDATE_HARD_FAILURE_KEYS,
            "candidate_boolean_hard_failure_keys": CANDIDATE_BOOLEAN_HARD_FAILURE_KEYS,
            "candidate_numeric_hard_failure_keys": CANDIDATE_NUMERIC_HARD_FAILURE_KEYS,
            "candidate_audit_status_values": CANDIDATE_AUDIT_STATUS_VALUES,
            "candidate_decision_gate_values": CANDIDATE_DECISION_GATE_VALUES,
            "candidate_promotion_interpretation_values": CANDIDATE_PROMOTION_INTERPRETATION_VALUES,
            "candidate_pass_value": CANDIDATE_PASS_VALUE,
            "candidate_fail_value": CANDIDATE_FAIL_VALUE,
            "candidate_not_recorded_value": CANDIDATE_NOT_RECORDED_VALUE,
            "candidate_gate_pass_interpretation": CANDIDATE_GATE_PASS_INTERPRETATION,
            "candidate_refined_boundary_scan_method": CANDIDATE_REFINED_BOUNDARY_SCAN_METHOD,
            "candidate_pit_universe_interval_type": CANDIDATE_PIT_UNIVERSE_INTERVAL_TYPE,
            "candidate_feature_readiness_policy": CANDIDATE_FEATURE_READINESS_POLICY,
        }

    def candidate_promotion_decision(self, candidate_start: str | date) -> dict[str, Any]:
        point = _as_date(candidate_start).isoformat()
        matches = [
            row for row in self.candidate_promotion_decisions
            if row.get("candidate_start") == point
        ]
        if len(matches) != 1:
            raise LookupError(f"Expected one candidate promotion decision for {point}, found {len(matches)}")
        return dict(matches[0])

    def earliest_candidate_gate_pass_date(self) -> date | None:
        """Return the earliest candidate start whose candidate gates pass, if any."""
        return self.earliest_candidate_gate_pass_start

    def refined_earliest_candidate_gate_pass_boundary(self) -> date | None:
        """Return the earliest monthly/session boundary whose candidate universe gates pass."""
        return self._refined_earliest_candidate_gate_pass_boundary

    def candidate_pit_universe_ready(self, as_of_date: str | date) -> bool:
        """Return whether a date is inside the refined candidate PIT-universe interval."""
        point = _as_date(as_of_date)
        boundary = self._refined_earliest_candidate_gate_pass_boundary
        if boundary is None or point < boundary:
            return False
        if self.coverage_end and point > self.coverage_end:
            return False
        return True

    def candidate_gate_pass_start_dates(self) -> list[date]:
        """Return candidate starts whose promotion gates pass, sorted chronologically."""
        configured_candidate_starts = {
            _as_date(candidate_start)
            for candidate_start in CANDIDATE_RESEARCH_START_DATES
        }
        gate_pass_start_dates = []
        for row in self.candidate_promotion_decisions:
            if "candidate_start" not in row:
                continue
            candidate_start = _as_date(row["candidate_start"])
            if candidate_start not in configured_candidate_starts:
                continue
            if row.get("candidate_audit_status") != CANDIDATE_PASS_VALUE:
                continue
            if any(row.get(field) != CANDIDATE_PASS_VALUE for field in CANDIDATE_DECISION_GATE_KEYS):
                continue
            if row.get("promotion_interpretation") != CANDIDATE_GATE_PASS_INTERPRETATION:
                continue
            gate_pass_start_dates.append(candidate_start)
        return sorted(gate_pass_start_dates)

    def candidate_gate_pass_ready(self, candidate_start: str | date) -> bool:
        """Return whether one configured candidate start has passing promotion gates."""
        point = _as_date(candidate_start)
        if point.isoformat() not in CANDIDATE_RESEARCH_START_DATES:
            raise ValueError(f"candidate_start is not configured: {point.isoformat()}")
        return point in set(self.candidate_gate_pass_start_dates())

    def candidate_research_ready(self, candidate_start: str | date) -> bool:
        """Return whether one candidate start is both gate-pass and research-high-confidence."""
        return (
            self.candidate_gate_pass_ready(candidate_start)
            and self.research_quality_on(candidate_start) == RESEARCH_HIGH_CONFIDENCE_STATUS
        )

    def candidate_research_ready_start_dates(self) -> list[date]:
        """Return configured candidate starts that are both gate-pass and research-high-confidence."""
        return [
            candidate_start
            for candidate_start in self.candidate_gate_pass_start_dates()
            if self.candidate_research_ready(candidate_start)
        ]

    def get_active_universe(self, as_of_date: str | date) -> list[dict[str, Any]]:
        return self.active_on(as_of_date)

    def get_investable_universe(self, as_of_date: str | date, **kwargs: Any) -> list[dict[str, Any]]:
        return self.eligible_on(as_of_date, **kwargs)

    @classmethod
    def from_jsonl(cls, root: str | Path = ".", *, strict: bool = False) -> "DataPlatform":
        platform = cls(root, strict=strict)
        base = platform.root
        def load(name: str) -> list[dict[str, Any]]:
            path = base / name
            return read_jsonl(path) if path.exists() else []
        platform.security_master = SecurityMaster(load("data/canonical/security_master.jsonl"))
        platform.company_names = CompanyNameHistoryStore(load("data/canonical/company_name_history.jsonl"))
        platform.isins = IsinHistoryStore(load("data/canonical/isin_history.jsonl"))
        prices_path = base / "data/canonical/daily_prices_raw.jsonl"
        adjusted_path = base / "data/derived/daily_prices_adjusted.jsonl"
        universe_path = base / "data/derived/active_universe_daily.jsonl"
        platform.prices = FilePriceStore(prices_path) if prices_path.exists() else PriceStore()
        platform.adjusted_prices = FilePriceStore(adjusted_path) if adjusted_path.exists() else PriceStore()
        platform.universe = FileUniverseStore(universe_path) if universe_path.exists() else UniverseStore()
        platform.research_universe = platform.universe
        status_path = base / "data/derived/trading_status_intervals_v4.parquet"
        platform.status = ParquetStatusStore(status_path) if status_path.exists() else StatusStore()
        return platform

    @classmethod
    def from_release(cls, release: str | Path, *, strict: bool = False) -> "DataPlatform":
        base = Path(release)
        platform = cls(base, strict=strict)
        manifest_path = base / DATA_RELEASE_MANIFEST_ARTIFACT
        if manifest_path.exists():
            import json
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            coverage = manifest.get("coverage", {})
            platform.coverage_start = _as_date(coverage["observed_start"]) if coverage.get("observed_start") else None
            platform.coverage_end = _as_date(coverage["observed_end"]) if coverage.get("observed_end") else None
            platform.verified_start = _as_date(manifest["verified_start_date"]) if manifest.get("verified_start_date") else None
            platform.verified_end = _as_date(manifest["verified_end_date"]) if manifest.get("verified_end_date") else None
            platform.quality_tier = manifest.get("quality_tier")
            platform.warmup_coverage = manifest.get("warmup_coverage") or {}
            platform.research_quality_intervals = manifest.get("research_quality_intervals") or []
            has_data_candidate_decisions = "candidate_promotion_decisions" in manifest
            has_data_earliest_candidate = "earliest_candidate_gate_pass_start" in manifest
            has_data_refined_candidate_boundary = "refined_earliest_candidate_gate_pass_boundary" in manifest
            if has_data_candidate_decisions != has_data_earliest_candidate:
                raise ValueError(
                    "data manifest candidate_promotion_decisions and "
                    "earliest_candidate_gate_pass_start must be provided together"
                )
            if has_data_refined_candidate_boundary and not has_data_candidate_decisions:
                raise ValueError(
                    "data manifest refined_earliest_candidate_gate_pass_boundary and "
                    "candidate_promotion_decisions must be provided together"
                )
            platform.candidate_promotion_decisions = _normalize_candidate_promotion_decisions(
                manifest.get("candidate_promotion_decisions")
            )
            has_data_refined_candidate_rows = any(
                "refined_earliest_passing_snapshot" in row
                for row in platform.candidate_promotion_decisions
            )
            if has_data_refined_candidate_rows and not has_data_refined_candidate_boundary:
                raise ValueError(
                    "data manifest refined_earliest_candidate_gate_pass_boundary must be provided "
                    "when candidate_promotion_decisions include refined_earliest_passing_snapshot"
                )
            platform.earliest_candidate_gate_pass_start = _normalize_earliest_candidate_gate_pass_start(
                manifest.get("earliest_candidate_gate_pass_start"),
                platform.candidate_promotion_decisions,
            )
            if has_data_refined_candidate_boundary:
                platform._refined_earliest_candidate_gate_pass_boundary = _normalize_refined_earliest_candidate_gate_pass_boundary(
                    manifest.get("refined_earliest_candidate_gate_pass_boundary"),
                    platform.candidate_promotion_decisions,
                )
            _validate_candidate_interval_recommendations(
                "data manifest",
                manifest,
                platform._refined_earliest_candidate_gate_pass_boundary,
                required=has_data_refined_candidate_boundary,
            )
            _validate_research_quality_intervals_after_warmup(
                "data manifest",
                platform.research_quality_intervals,
                platform.warmup_coverage,
                platform._refined_earliest_candidate_gate_pass_boundary,
            )
        research_manifest_path = base / RESEARCH_RELEASE_MANIFEST_ARTIFACT
        if research_manifest_path.exists():
            import json
            research_manifest = json.loads(research_manifest_path.read_text(encoding="utf-8"))
            research_quality = research_manifest.get("research_quality", {})
            if research_quality.get("status") == RESEARCH_HIGH_CONFIDENCE_STATUS:
                platform.verified_start = _as_date(research_quality["start"]) if research_quality.get("start") else platform.verified_start
                platform.verified_end = _as_date(research_quality["end"]) if research_quality.get("end") else platform.verified_end
                platform.quality_tier = research_quality["status"]
            platform.warmup_coverage = research_manifest.get("warmup_coverage") or platform.warmup_coverage
            platform.research_quality_intervals = research_manifest.get("research_quality_intervals") or platform.research_quality_intervals
            _validate_research_quality_scalar_matches_interval(
                "research manifest",
                research_quality,
                platform.research_quality_intervals,
            )
            has_research_candidate_decisions = "candidate_promotion_decisions" in research_manifest
            has_research_earliest_candidate = "earliest_candidate_gate_pass_start" in research_manifest
            has_research_refined_candidate_boundary = "refined_earliest_candidate_gate_pass_boundary" in research_manifest
            if has_research_candidate_decisions != has_research_earliest_candidate:
                raise ValueError(
                    "research manifest candidate_promotion_decisions and "
                    "earliest_candidate_gate_pass_start must be provided together"
                )
            if has_research_refined_candidate_boundary and not has_research_candidate_decisions:
                raise ValueError(
                    "research manifest refined_earliest_candidate_gate_pass_boundary and "
                    "candidate_promotion_decisions must be provided together"
                )
            if has_research_candidate_decisions:
                platform.candidate_promotion_decisions = _normalize_candidate_promotion_decisions(
                    research_manifest.get("candidate_promotion_decisions")
                )
                has_research_refined_candidate_rows = any(
                    "refined_earliest_passing_snapshot" in row
                    for row in platform.candidate_promotion_decisions
                )
                if has_research_refined_candidate_rows and not has_research_refined_candidate_boundary:
                    raise ValueError(
                        "research manifest refined_earliest_candidate_gate_pass_boundary must be provided "
                        "when candidate_promotion_decisions include refined_earliest_passing_snapshot"
                    )
                platform.earliest_candidate_gate_pass_start = _normalize_earliest_candidate_gate_pass_start(
                    research_manifest.get("earliest_candidate_gate_pass_start"),
                    platform.candidate_promotion_decisions,
                )
                if has_research_refined_candidate_boundary:
                    platform._refined_earliest_candidate_gate_pass_boundary = _normalize_refined_earliest_candidate_gate_pass_boundary(
                        research_manifest.get("refined_earliest_candidate_gate_pass_boundary"),
                        platform.candidate_promotion_decisions,
                    )
                _validate_candidate_interval_recommendations(
                    "research manifest",
                    research_manifest,
                    platform._refined_earliest_candidate_gate_pass_boundary,
                    required=has_research_refined_candidate_boundary,
                )
            _validate_research_quality_intervals_after_warmup(
                "research manifest",
                platform.research_quality_intervals,
                platform.warmup_coverage,
                platform._refined_earliest_candidate_gate_pass_boundary,
            )
        import pyarrow.parquet as parquet
        master = parquet.read_table(base / "security_master.parquet").to_pylist()
        platform.security_master = SecurityMaster(master)
        company_names = base / "company_name_history.parquet"
        if company_names.exists():
            platform.company_names = ParquetCompanyNameHistoryStore(company_names)
        isin_history = base / "isin_history.parquet"
        if isin_history.exists():
            platform.isins = ParquetIsinHistoryStore(isin_history)
        platform.universe = ParquetUniverseStore(base / "active_universe_daily.parquet", base / "liquidity_features.parquet")
        research_path = base / "research_universe_monthly.parquet"
        platform.research_universe = ParquetUniverseStore(research_path) if research_path.exists() else platform.universe
        platform.prices = ParquetPriceStore(base / "daily_prices_raw.parquet")
        adjusted_path = base / "daily_prices_adjusted.parquet"
        platform.adjusted_prices = ParquetPriceStore(adjusted_path) if adjusted_path.exists() else PriceStore()
        status_path = base / "trading_status_intervals.parquet"
        platform.status = ParquetStatusStore(status_path) if status_path.exists() else StatusStore()
        terminal_path = base / "terminal_events.parquet"
        platform.terminal_events = TerminalEventStore(parquet.read_table(terminal_path).to_pylist() if terminal_path.exists() else [])
        calendar_path = base / "trading_calendar.parquet"
        platform.calendar = ParquetCalendarStore(calendar_path) if calendar_path.exists() else CalendarStore()
        return platform


def _normalize_dates(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    for key in ("date", "effective_from", "effective_to", "first_trade_date", "last_trade_date", "status_start", "status_end"):
        if isinstance(result.get(key), str):
            result[key] = date.fromisoformat(result[key])
    return result
