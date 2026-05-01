"""Decision text loader.

Loads a single decision file (PDF / HTML / plain-text fixture) into a raw
text string plus structured metadata. This is the I/O layer that the
proposition extractor (Task 6) sits on top of.

Design notes:
  - PDF extraction defers to :class:`rag_engine.extractors.pdf_extractor.PDFExtractor`
    so we share a single PDF library (PyMuPDF) across the codebase.
  - HTML uses the stdlib :mod:`html.parser` to avoid adding BeautifulSoup as
    a dependency. We strip ``<script>`` / ``<style>`` content and tags, then
    let :func:`normalize_for_matching` collapse whitespace downstream.
  - The 100-character minimum is checked against the *normalized* text so
    that a PDF full of whitespace and form-feeds still gets rejected.
  - Any extractor exception is wrapped in :class:`DecisionTextExtractionError`
    with the original cause attached.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

from .models import normalize_for_matching


_MIN_USEFUL_CHARS = 100

# Tags whose text content should be discarded entirely (not shown to the
# extractor). Anything else has its tags stripped but text retained.
_HTML_DROP_TAGS = frozenset({"script", "style", "head"})


# ---------------------------------------------------------------------------
# Result type / errors
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LoadedDecisionText:
    """Output of :func:`load_decision_text`.

    ``full_text`` is the *raw* extracted text (NOT normalized) — downstream
    code typically normalizes lazily with :func:`normalize_for_matching`.
    """

    full_text: str
    extraction_method: str  # "pymupdf_pdf" | "html_text" | "fixture_text"
    page_count: Optional[int]
    metadata: dict = field(default_factory=dict)


class DecisionTextExtractionError(Exception):
    """Raised when a decision file cannot be loaded into useful text.

    Failure cases:
      - File does not exist
      - File extension not supported
      - Underlying extractor raised an exception
      - Extracted text has fewer than ``_MIN_USEFUL_CHARS`` characters after
        normalization (likely a scanned/empty document)
    """


# ---------------------------------------------------------------------------
# HTML parsing (stdlib only)
# ---------------------------------------------------------------------------


class _HTMLTextExtractor(HTMLParser):
    """Minimal HTML→text stripper using the stdlib parser.

    We deliberately don't try to preserve list structure, table layout, etc.
    — the LLM extractor downstream consumes flat text and tribunal decisions
    rarely use elaborate markup beyond paragraphs and headings.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._drop_depth = 0  # nested-drop counter for <script>/<style>/<head>

    def handle_starttag(self, tag: str, attrs):  # noqa: ANN001 — stdlib signature
        if tag.lower() in _HTML_DROP_TAGS:
            self._drop_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in _HTML_DROP_TAGS and self._drop_depth > 0:
            self._drop_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._drop_depth == 0:
            self._chunks.append(data)

    def get_text(self) -> str:
        # Join with spaces so that "<p>A</p><p>B</p>" doesn't become "AB".
        return " ".join(chunk for chunk in self._chunks if chunk)


def _extract_html_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    parser = _HTMLTextExtractor()
    parser.feed(raw)
    parser.close()
    return parser.get_text()


# ---------------------------------------------------------------------------
# PDF parsing (delegates to rag_engine)
# ---------------------------------------------------------------------------


def _extract_pdf_text(path: Path) -> tuple[str, dict]:
    # Imported lazily to avoid forcing rag_engine onto the import path for
    # callers that only handle HTML/txt fixtures.
    from rag_engine.extractors.pdf_extractor import PDFExtractor

    extractor = PDFExtractor()
    return extractor.extract_from_pdf(path)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def load_decision_text(path: Path) -> LoadedDecisionText:
    """Load and extract text from a decision file.

    Dispatch by extension:

    - ``.pdf``           → :class:`PDFExtractor` (PyMuPDF)
    - ``.html`` / ``.htm`` → stdlib HTML stripper
    - ``.txt``           → read directly (test-fixture path)

    Raises :class:`DecisionTextExtractionError` on any failure, including
    unsupported extensions, missing files, extractor errors, or output
    shorter than 100 characters after normalization.
    """
    if not path.exists():
        raise DecisionTextExtractionError(
            f"Decision file does not exist: {path}"
        )

    suffix = path.suffix.lower()

    if suffix == ".pdf":
        try:
            full_text, pdf_metadata = _extract_pdf_text(path)
        except DecisionTextExtractionError:
            raise
        except Exception as exc:  # pragma: no cover — defensive wrap
            raise DecisionTextExtractionError(
                f"PDF extraction failed for {path}: {exc}"
            ) from exc

        _ensure_useful(full_text, path)
        page_count = pdf_metadata.get("page_count") if isinstance(pdf_metadata, dict) else None
        return LoadedDecisionText(
            full_text=full_text,
            extraction_method="pymupdf_pdf",
            page_count=page_count,
            metadata=dict(pdf_metadata) if isinstance(pdf_metadata, dict) else {},
        )

    if suffix in {".html", ".htm"}:
        try:
            full_text = _extract_html_text(path)
        except Exception as exc:
            raise DecisionTextExtractionError(
                f"HTML extraction failed for {path}: {exc}"
            ) from exc

        _ensure_useful(full_text, path)
        return LoadedDecisionText(
            full_text=full_text,
            extraction_method="html_text",
            page_count=None,
            metadata={},
        )

    if suffix == ".txt":
        try:
            full_text = path.read_text(encoding="utf-8")
        except Exception as exc:
            raise DecisionTextExtractionError(
                f"Text fixture read failed for {path}: {exc}"
            ) from exc

        _ensure_useful(full_text, path)
        return LoadedDecisionText(
            full_text=full_text,
            extraction_method="fixture_text",
            page_count=None,
            metadata={},
        )

    raise DecisionTextExtractionError(
        f"Unsupported decision file extension {suffix!r}: {path}"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_useful(full_text: str, path: Path) -> None:
    """Reject too-short extractions (likely scanned PDFs or empty files)."""
    normalized_len = len(normalize_for_matching(full_text))
    if normalized_len < _MIN_USEFUL_CHARS:
        raise DecisionTextExtractionError(
            f"Extracted text too short ({normalized_len} chars after "
            f"normalization, need >= {_MIN_USEFUL_CHARS}): {path}"
        )


__all__ = [
    "LoadedDecisionText",
    "DecisionTextExtractionError",
    "load_decision_text",
]
