from __future__ import annotations

import csv
import io
import zipfile
from datetime import date
from typing import Any, Iterator

from .models import DailyObservation

RAW_EXECUTION_SERIES = {"EQ", "BE"}


def legacy_url(point: date) -> str:
    month = point.strftime("%b").upper()
    return f"https://archives.nseindia.com/content/historical/EQUITIES/{point:%Y}/{month}/cm{point:%d}{month}{point:%Y}bhav.csv.zip"


def legacy_url_correct(point: date) -> str:
    return legacy_url(point)


def udiff_url(point: date) -> str:
    return f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{point:%Y%m%d}_F_0000.csv.zip"


def candidate_urls(point: date) -> list[str]:
    return [legacy_url_correct(point), udiff_url(point)]


def _number(value: str | None) -> float | None:
    if value is None or not value.strip() or value.strip() in {"-", "NA", "null"}:
        return None
    return float(value.replace(",", "").strip())


def _int(value: str | None) -> int | None:
    number = _number(value)
    return None if number is None else int(number)


def _first(row: dict[str, str], *names: str) -> str | None:
    for name in names:
        if name in row:
            return row[name]
    return None


def parse_bhavcopy(content: bytes, trade_date: date, source_file_id: str, source_sha256: str) -> Iterator[DailyObservation]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith((".csv", ".txt"))]
        if not names:
            raise ValueError("Archive has no CSV/TXT member")
        raw = archive.read(names[0]).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames:
        raise ValueError("Bhavcopy has no header")
    normalized = {field.strip().upper().replace(" ", "_"): field for field in reader.fieldnames if field}
    required = ({"SYMBOL", "SERIES"}, {"TCKRSYMB", "SCTYSRS"})
    if not any(fields.issubset(normalized) for fields in required):
        raise ValueError(f"Unrecognized bhavcopy columns: {reader.fieldnames}")
    for original in reader:
        row = {key.strip().upper().replace(" ", "_"): value for key, value in original.items() if key}
        series = (_first(row, "SERIES", "SCTYSRS") or "").strip().upper()
        if series not in RAW_EXECUTION_SERIES:
            continue
        symbol = (_first(row, "SYMBOL", "TCKRSYMB") or "").strip().upper()
        if not symbol:
            continue
        isin = (_first(row, "ISIN") or "").strip().upper() or None
        company_name = (_first(row, "NAME", "SECURITY_NAME", "FININSTRMNM") or "").strip() or None
        yield DailyObservation(date=trade_date, exchange="NSE", symbol=symbol, series=series, security_id=None, open=_number(_first(row, "OPEN", "OPEN_PRICE", "OPNPRIC")), high=_number(_first(row, "HIGH", "HIGH_PRICE", "HGHPric".upper())), low=_number(_first(row, "LOW", "LOW_PRICE", "LWPRIC")), close=_number(_first(row, "CLOSE", "CLOSE_PRICE", "CLSPRIC")), volume=_int(_first(row, "VOLUME", "TOTTRDQTY", "TOTAL_TRADED_QUANTITY", "TTLTRADGVOL")), traded_value=_number(_first(row, "NET_TURNOV", "TOTTRDVAL", "TOTAL_TRADED_VALUE", "TTLTRFVAL")), source_file_id=source_file_id, source_sha256=source_sha256, source_quality="NSE_OFFICIAL_BHAVCOPY", isin=isin, company_name=company_name)
