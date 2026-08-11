from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Iterable

from .profiles import LIQUID_V1_DEFINITION, TOP_LIQUIDITY_RANKING_METRIC
from .storage import iter_jsonl, read_jsonl


def _as_date(value: str | date) -> date:
    return date.fromisoformat(value) if isinstance(value, str) else value


class CoverageError(ValueError):
    """The requested date is outside the trusted release coverage."""


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
            and row.get("instrument_type") == "ORDINARY_EQUITY"
            and row.get("trading_status") == "ACTIVE_TRADING"
        ]
        return sorted(rows, key=lambda row: row[metric], reverse=True)[:n]

    def profile_on(self, as_of_date: str | date, profile: str = "LIQUID_V1") -> list[dict[str, Any]]:
        point = _as_date(as_of_date)
        if profile != "LIQUID_V1":
            raise ValueError(f"Unknown universe profile: {profile}")
        rows = [row for row in self.rows if row.get("date") == point and self._liquid_v1_eligible(row)]
        for row in rows:
            row.setdefault("profile_id", "NSE_BROAD_LIQUID_PIT_V1")
            row.setdefault("profile_version", profile)
            row.setdefault("as_of_date", point)
            row.setdefault("eligibility_result", "ELIGIBLE")
            row.setdefault("eligibility_reason_codes", "PASSED_LIQUID_V1")
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

    def ranked_liquid_on(self, as_of_date: str | date, n: int, *, metric: str = "median_traded_value_126") -> list[dict[str, Any]]:
        rows = [
            row for row in self.active_on(as_of_date)
            if row.get(metric) is not None
            and row.get("instrument_type") == "ORDINARY_EQUITY"
            and row.get("trading_status") == "ACTIVE_TRADING"
        ]
        return sorted(rows, key=lambda row: row[metric], reverse=True)[:n]

    def profile_on(self, as_of_date: str | date, profile: str = "LIQUID_V1") -> list[dict[str, Any]]:
        if profile != "LIQUID_V1":
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
            row.setdefault("profile_id", "NSE_BROAD_LIQUID_PIT_V1")
            row.setdefault("profile_version", profile)
            row.setdefault("as_of_date", point)
            row.setdefault("eligibility_result", "ELIGIBLE")
            row.setdefault("eligibility_reason_codes", "PASSED_LIQUID_V1")
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

    def profile_on(self, as_of_date: str | date, profile: str = "LIQUID_V1") -> list[dict[str, Any]]:
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
        manifest_path = base / "data_release_manifest.json"
        if manifest_path.exists():
            import json
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            coverage = manifest.get("coverage", {})
            platform.coverage_start = _as_date(coverage["observed_start"]) if coverage.get("observed_start") else None
            platform.coverage_end = _as_date(coverage["observed_end"]) if coverage.get("observed_end") else None
            platform.verified_start = _as_date(manifest["verified_start_date"]) if manifest.get("verified_start_date") else None
            platform.verified_end = _as_date(manifest["verified_end_date"]) if manifest.get("verified_end_date") else None
            platform.quality_tier = manifest.get("quality_tier")
        research_manifest_path = base / "research_release_manifest.json"
        if research_manifest_path.exists():
            import json
            research_manifest = json.loads(research_manifest_path.read_text(encoding="utf-8"))
            research_quality = research_manifest.get("research_quality", {})
            if research_quality.get("status") == "RESEARCH_HIGH_CONFIDENCE":
                platform.verified_start = _as_date(research_quality["start"]) if research_quality.get("start") else platform.verified_start
                platform.verified_end = _as_date(research_quality["end"]) if research_quality.get("end") else platform.verified_end
                platform.quality_tier = research_quality["status"]
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
