"""Tests for decision text loader (SHA-36 Task 5).

TDD: written before text_loader.py exists. Tests should fail with
ImportError until the module is implemented.
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF — already a project dependency
import pytest

from kg_builder.propositions.text_loader import (
    DecisionTextExtractionError,
    LoadedDecisionText,
    load_decision_text,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_pdf(path: Path, text: str) -> None:
    """Write a minimal single-page PDF containing `text`."""
    doc = fitz.open()
    page = doc.new_page()
    if text:
        page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_load_pdf_uses_extract_from_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "decision.pdf"
    body = (
        "This is a tribunal decision concerning a tenancy deposit dispute. "
        "The deposit of one thousand pounds was protected late, breaching "
        "section 213 of the Housing Act 2004."
    )
    _write_pdf(pdf_path, body)

    result = load_decision_text(pdf_path)

    assert isinstance(result, LoadedDecisionText)
    assert result.extraction_method == "pymupdf_pdf"
    assert len(result.full_text) > 100
    assert result.page_count == 1
    assert isinstance(result.metadata, dict)


def test_load_pdf_raises_on_empty_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "empty.pdf"
    _write_pdf(pdf_path, "")  # blank page

    with pytest.raises(DecisionTextExtractionError):
        load_decision_text(pdf_path)


def test_load_html_strips_tags(tmp_path: Path) -> None:
    html_path = tmp_path / "decision.html"
    # Pad with enough text to exceed the 100-char minimum.
    html_path.write_text(
        "<html><body>"
        "<p>The deposit was protected late.</p>"
        "<p>Section 213 of the Housing Act 2004 imposes a 30-day deadline "
        "for the protection of any tenancy deposit received by a landlord.</p>"
        "</body></html>",
        encoding="utf-8",
    )

    result = load_decision_text(html_path)

    assert result.extraction_method == "html_text"
    assert "The deposit was protected late." in result.full_text
    assert "<p>" not in result.full_text
    assert "</p>" not in result.full_text
    assert result.page_count is None


def test_load_txt_returns_raw(tmp_path: Path) -> None:
    txt_path = tmp_path / "decision.txt"
    raw = "A" * 200
    txt_path.write_text(raw, encoding="utf-8")

    result = load_decision_text(txt_path)

    assert result.extraction_method == "fixture_text"
    assert result.full_text == raw
    assert result.page_count is None


def test_load_unsupported_extension_raises(tmp_path: Path) -> None:
    docx_path = tmp_path / "decision.docx"
    docx_path.write_bytes(b"PK\x03\x04 not a real docx")

    with pytest.raises(DecisionTextExtractionError):
        load_decision_text(docx_path)


def test_load_missing_file_raises(tmp_path: Path) -> None:
    missing = tmp_path / "nope.pdf"

    with pytest.raises(DecisionTextExtractionError):
        load_decision_text(missing)
