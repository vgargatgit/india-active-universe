from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "collect_nse_suspension_evidence.py"
SPEC = importlib.util.spec_from_file_location("collect_nse_suspension_evidence_manifest", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _selected() -> list[dict[str, str]]:
    return [
        {"source_url": "https://nsearchives.nseindia.com/content/press/01012007.htm"},
        {"source_url": "https://nsearchives.nseindia.com/content/press/02012007.pdf"},
    ]


def test_manifest_contract_accepts_exactly_one_terminal_row_per_source() -> None:
    archive = module.ARCHIVE_URL
    module.validate_source_manifest(
        archive_url=archive,
        selected=_selected(),
        source_rows=[
            {"source_url": archive, "download_status": "DOWNLOADED"},
            {
                "source_url": "https://nsearchives.nseindia.com/content/press/01012007.htm",
                "download_status": "DOWNLOADED",
            },
            {
                "source_url": "https://nsearchives.nseindia.com/content/press/02012007.pdf",
                "download_status": "FAILED:ValueError",
            },
        ],
    )


def test_manifest_contract_rejects_duplicate_terminal_rows() -> None:
    archive = module.ARCHIVE_URL
    duplicated = "https://nsearchives.nseindia.com/content/press/01012007.htm"
    with pytest.raises(ValueError, match="one-to-one"):
        module.validate_source_manifest(
            archive_url=archive,
            selected=_selected(),
            source_rows=[
                {"source_url": archive, "download_status": "DOWNLOADED"},
                {"source_url": duplicated, "download_status": "DOWNLOADED"},
                {"source_url": duplicated, "download_status": "FAILED:ValueError"},
                {
                    "source_url": "https://nsearchives.nseindia.com/content/press/02012007.pdf",
                    "download_status": "DOWNLOADED",
                },
            ],
        )


def test_manifest_contract_rejects_missing_selected_source() -> None:
    with pytest.raises(ValueError, match="missing"):
        module.validate_source_manifest(
            archive_url=module.ARCHIVE_URL,
            selected=_selected(),
            source_rows=[
                {
                    "source_url": module.ARCHIVE_URL,
                    "download_status": "DOWNLOADED",
                },
                {
                    "source_url": "https://nsearchives.nseindia.com/content/press/01012007.htm",
                    "download_status": "DOWNLOADED",
                },
            ],
        )
