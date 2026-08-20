from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "collect_nse_suspension_evidence.py"
SPEC = importlib.util.spec_from_file_location("collect_nse_suspension_evidence", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_archive_candidates_select_only_status_related_html_and_pdf() -> None:
    archive = b"""
    <html><body>
      <a href="https://nsearchives.nseindia.com/content/press/30112006.htm">Nov 30, 2006</a>
      <ul><li>NSE completes normal settlement</li></ul>
      <a href="https://nsearchives.nseindia.com/content/press/01122006.pdf">Dec 01, 2006</a>
      <ul><li>Recommencement of trading pursuant to scheme of arrangement - MANALIPETC</li></ul>
      <a href="/content/press/08082007.htm">Aug 08, 2007</a>
      <ul><li>Proposed suspension of securities</li><li>Market-wide Position Limit</li></ul>
      <a href="/content/press/09082007.htm">Aug 09, 2007</a>
      <ul><li>NSE completes normal settlement</li></ul>
    </body></html>
    """

    rows = module.archive_candidates(
        module.ARCHIVE_URL,
        archive,
        start="2006-01-01",
        end="2026-08-10",
    )

    assert [row["publication_date"] for row in rows] == [
        "2006-12-01",
        "2007-08-08",
    ]
    assert rows[0]["document_type"] == "pdf"
    assert rows[1]["document_type"] == "htm"
    assert rows[1]["source_url"].endswith("/content/press/08082007.htm")
    assert "suspension" in rows[1]["archive_context"].lower()


def test_archive_candidates_do_not_select_complaint_table_without_status_title() -> None:
    archive = b"""
    <html><body>
      <a href="/content/press/05032015.htm">Mar 05, 2015</a>
      <ul><li>Corporates with highest number of complaints pending</li></ul>
      <a href="/content/press/06032015.htm">Mar 06, 2015</a>
      <ul><li>NSE completes normal settlement</li></ul>
    </body></html>
    """

    assert module.archive_candidates(
        module.ARCHIVE_URL,
        archive,
        start="2006-01-01",
        end="2026-08-10",
    ) == []


def test_alternate_nse_url_switches_archive_and_www_hosts() -> None:
    archive = "https://nsearchives.nseindia.com/content/press/08082007.htm"
    public = "https://www.nseindia.com/content/press/08082007.htm"
    assert module.alternate_nse_url(archive) == public
    assert module.alternate_nse_url(public) == archive
    assert module.alternate_nse_url("https://example.com/x") is None


def test_fetch_uses_alternate_official_host_after_primary_failure(monkeypatch) -> None:
    primary = "https://nsearchives.nseindia.com/content/press/08082007.htm"
    alternate = "https://www.nseindia.com/content/press/08082007.htm"
    calls: list[str] = []

    def fake_request(url: str):
        calls.append(url)
        if url == primary:
            raise OSError("primary unavailable")
        return module.FetchedDocument(b"<html>ok</html>", "text/html", url)

    monkeypatch.setattr(module, "_request_once", fake_request)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)

    result = module.fetch(primary, attempts=2)

    assert result.resolved_url == alternate
    assert calls == [primary, primary, alternate]


def test_document_text_supports_html_and_pdf(monkeypatch) -> None:
    html_document = module.FetchedDocument(
        b"<html><body><h1>Suspension of trading</h1><p>Example Limited</p></body></html>",
        "text/html",
        "official",
    )
    assert "Suspension of trading" in module.document_text(html_document)

    class FakePage:
        def extract_text(self):
            return "Recommencement of trading - Example Limited"

    class FakeReader:
        def __init__(self, _stream):
            self.pages = [FakePage()]

    monkeypatch.setattr(module, "PdfReader", FakeReader)
    pdf_document = module.FetchedDocument(
        b"%PDF-fake",
        "application/pdf",
        "official-pdf",
    )
    assert module.document_text(pdf_document) == "Recommencement of trading - Example Limited"


def test_effective_date_and_event_type_cover_suspension_and_recommencement() -> None:
    suspended = (
        "The equity shares of Example Limited will be suspended from trading "
        "w.e.f August 17, 2007 until further notice."
    )
    resumed = (
        "Recommencement of trading in Manali Petrochemical Limited "
        "w.e.f. December 6, 2006."
    )
    assert module.effective_date(suspended) == "2007-08-17"
    assert module.event_type(suspended) == "SUSPENSION_START"
    assert module.effective_date(resumed) == "2006-12-06"
    assert module.event_type(resumed) == "SUSPENSION_REVOKED"


def test_failed_source_helpers_only_count_selected_source_failures() -> None:
    rows = [
        {"download_status": "DOWNLOADED"},
        {"download_status": "FAILED:OSError", "source_url": "a"},
        {"download_status": "FAILED:ValueError", "source_url": "b"},
    ]
    assert module.source_failure_count(rows) == 2
    assert [row["source_url"] for row in module.failed_sources(rows)] == ["a", "b"]
