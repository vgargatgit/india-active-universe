from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Iterable

from .storage import iter_jsonl, read_jsonl


def _as_date(value: str | date) -> date:
    return date.fromisoformat(value) if isinstance(value, str) else value


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

    def eligible_on(self, as_of_date: str | date, *, min_price: float | None = None, min_history_sessions: int = 0, min_median_traded_value_60: float | None = None) -> list[dict[str, Any]]:
        rows = self.active_on(as_of_date)
        return [row for row in rows if (min_price is None or (row.get("close") is not None and row["close"] >= min_price)) and row.get("history_sessions", 0) >= min_history_sessions and (min_median_traded_value_60 is None or row.get("median_traded_value_60", 0) >= min_median_traded_value_60)]

    def ranked_liquid_on(self, as_of_date: str | date, n: int, *, metric: str = "median_traded_value_126") -> list[dict[str, Any]]:
        rows = [row for row in self.active_on(as_of_date) if row.get(metric) is not None]
        return sorted(rows, key=lambda row: row[metric], reverse=True)[:n]


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
        output = []
        for batch in parquet.ParquetFile(self.path).iter_batches(batch_size=25_000):
            for row in batch.to_pylist():
                if str(row.get("date"))[:10] == point and row.get("active") is True:
                    output.append(row)
        if self.features_path and self.features_path.exists() and output:
            feature_rows = parquet.read_table(self.features_path, filters=[("date", "=", point)]).to_pylist()
            by_security = {row["security_id"]: row for row in feature_rows}
            for row in output:
                feature = by_security.get(row["security_id"], {})
                for key in ("history_sessions", "listing_age_sessions", "listing_age_calendar_days", "price", "series", "listing_status", "valid_trade_days_20", "valid_trade_days_60", "valid_trade_days_126", "valid_trade_days_252", "zero_volume_days_20", "zero_volume_days_60", "zero_volume_days_126", "zero_volume_days_252", "median_traded_value_20", "median_traded_value_60", "median_traded_value_126", "median_traded_value_252", "average_traded_value_20", "average_traded_value_60", "average_traded_value_126", "average_traded_value_252", "stale_price_days_60", "liquidity_percentile_60", "liquidity_bucket_60", "feature_as_of_date"):
                    if key in feature:
                        row[key] = feature[key]
        return output

    def ranked_liquid_on(self, as_of_date: str | date, n: int, *, metric: str = "median_traded_value_126") -> list[dict[str, Any]]:
        rows = [row for row in self.active_on(as_of_date) if row.get(metric) is not None]
        return sorted(rows, key=lambda row: row[metric], reverse=True)[:n]


class DataPlatform:
    def __init__(self, root: str | Path = ".") -> None:
        self.root = Path(root)
        self.security_master = SecurityMaster()
        self.prices = PriceStore()
        self.universe = UniverseStore()

    @classmethod
    def from_jsonl(cls, root: str | Path = ".") -> "DataPlatform":
        platform = cls(root)
        base = platform.root
        def load(name: str) -> list[dict[str, Any]]:
            path = base / name
            return read_jsonl(path) if path.exists() else []
        platform.security_master = SecurityMaster(load("data/canonical/security_master.jsonl"))
        prices_path = base / "data/canonical/daily_prices_raw.jsonl"
        universe_path = base / "data/derived/active_universe_daily.jsonl"
        platform.prices = FilePriceStore(prices_path) if prices_path.exists() else PriceStore()
        platform.universe = FileUniverseStore(universe_path) if universe_path.exists() else UniverseStore()
        return platform

    @classmethod
    def from_release(cls, release: str | Path) -> "DataPlatform":
        base = Path(release)
        platform = cls(base)
        import pyarrow.parquet as parquet
        master = parquet.read_table(base / "security_master.parquet").to_pylist()
        platform.security_master = SecurityMaster(master)
        platform.universe = ParquetUniverseStore(base / "active_universe_daily.parquet", base / "liquidity_features.parquet")
        platform.prices = ParquetPriceStore(base / "daily_prices_raw.parquet")
        return platform


def _normalize_dates(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    for key in ("date", "effective_from", "effective_to", "first_trade_date", "last_trade_date"):
        if isinstance(result.get(key), str):
            result[key] = date.fromisoformat(result[key])
    return result
