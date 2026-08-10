#!/usr/bin/env python3
"""Validate that a cached NSE response is a usable historical market archive."""

from __future__ import annotations

import csv
import io
import sys
import zipfile
from pathlib import Path


def validate(path: str | Path) -> tuple[bool, str]:
    archive = Path(path)
    if not archive.is_file() or archive.stat().st_size == 0:
        return False, "EMPTY_FILE"
    if not zipfile.is_zipfile(archive):
        return False, "NOT_A_ZIP_ARCHIVE"
    try:
        with zipfile.ZipFile(archive) as zf:
            members = [name for name in zf.namelist() if name.lower().endswith((".csv", ".txt"))]
            if not members:
                return False, "NO_CSV_MEMBER"
            header = zf.open(members[0]).readline().decode("utf-8-sig", errors="replace")
    except (OSError, zipfile.BadZipFile, UnicodeError) as exc:
        return False, f"ARCHIVE_READ_ERROR:{type(exc).__name__}"
    fields = {field.strip().upper().replace(" ", "_") for field in next(csv.reader(io.StringIO(header)), [])}
    if not ({"SYMBOL", "SERIES"} <= fields or {"TCKRSYMB", "SCTYSRS"} <= fields):
        return False, "MISSING_REQUIRED_MARKET_COLUMNS"
    return True, "VALID_NSE_MARKET_ARCHIVE"


if __name__ == "__main__":
    valid, message = validate(sys.argv[1])
    print(message)
    raise SystemExit(0 if valid else 1)
