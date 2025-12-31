"""
PDF text extraction using PyMuPDF.

Extracts text content from tribunal decision PDFs while preserving
paragraph structure and handling various PDF formats.
"""

import json
import re
from pathlib import Path
from typing import Optional, Tuple

import fitz  # PyMuPDF
import structlog

from ..config import CaseDocument

logger = structlog.get_logger()


class PDFExtractor:
    """
    Extract text content from tribunal decision PDFs.

    Uses PyMuPDF for reliable text extraction with fallback handling
    for corrupted or image-based PDFs.
    """

    def __init__(self) -> None:
        """Initialize the PDF extractor."""
        self.extraction_stats = {
            "total_processed": 0,
            "successful": 0,
            "failed": 0,
            "empty_content": 0,
        }

    def extract_from_pdf(self, pdf_path: Path) -> Tuple[str, dict]:
        """
        Extract text from a single PDF file.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            Tuple of (extracted_text, metadata_dict)

        Raises:
            ValueError: If PDF cannot be opened or has no extractable text
        """
        self.extraction_stats["total_processed"] += 1

        if not pdf_path.exists():
            raise ValueError(f"PDF file not found: {pdf_path}")

        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            self.extraction_stats["failed"] += 1
            logger.error("failed_to_open_pdf", path=str(pdf_path), error=str(e))
            raise ValueError(f"Failed to open PDF: {e}")

        try:
            # Extract text from all pages
            text_parts = []
            for page_num, page in enumerate(doc):
                page_text = page.get_text("text")
                if page_text.strip():
                    text_parts.append(page_text)

            full_text = "\n\n".join(text_parts)

            # Check if we got any content
            if not full_text.strip():
                self.extraction_stats["empty_content"] += 1
                logger.warning(
                    "empty_pdf_content",
                    path=str(pdf_path),
                    page_count=len(doc)
                )
                raise ValueError(f"No extractable text in PDF: {pdf_path}")

            # Extract metadata from PDF
            metadata = {
                "page_count": len(doc),
                "title": doc.metadata.get("title", ""),
                "author": doc.metadata.get("author", ""),
                "creation_date": doc.metadata.get("creationDate", ""),
            }

            self.extraction_stats["successful"] += 1
            logger.debug(
                "pdf_extracted",
                path=str(pdf_path),
                chars=len(full_text),
                pages=len(doc)
            )

            return full_text, metadata

        finally:
            doc.close()

    def extract_case_document(
        self,
        pdf_path: Path,
        metadata_path: Optional[Path] = None
    ) -> CaseDocument:
        """
        Extract a complete CaseDocument from a PDF and optional metadata.json.

        Args:
            pdf_path: Path to the PDF file
            metadata_path: Optional path to metadata.json (will look for it automatically)

        Returns:
            CaseDocument with extracted content and metadata
        """
        # Extract PDF text
        full_text, pdf_metadata = self.extract_from_pdf(pdf_path)

        # Load companion metadata.json if it exists
        if metadata_path is None:
            metadata_path = pdf_path.parent / "metadata.json"

        case_metadata = {}
        if metadata_path.exists():
            try:
                with open(metadata_path, "r", encoding="utf-8") as f:
                    case_metadata = json.load(f)
            except Exception as e:
                logger.warning(
                    "failed_to_load_metadata",
                    path=str(metadata_path),
                    error=str(e)
                )

        # Parse case reference from path or metadata
        case_reference = case_metadata.get(
            "case_reference",
            self._extract_case_reference(pdf_path)
        )

        # Parse year from path or metadata
        year = case_metadata.get("year") or self._extract_year(pdf_path)

        return CaseDocument(
            case_reference=case_reference,
            year=year,
            region=case_metadata.get("region_code"),
            region_name=case_metadata.get("region_name"),
            case_type=case_metadata.get("case_type_code"),
            case_type_name=case_metadata.get("case_type_name"),
            title=case_metadata.get("title") or pdf_metadata.get("title"),
            decision_date=case_metadata.get("decision_date"),
            full_text=full_text,
            sections={},  # Will be populated by text processing
            source_path=str(pdf_path),
            metadata={
                **pdf_metadata,
                "deposit_keywords_matched": case_metadata.get("deposit_keywords_matched", []),
                "adjacent_keywords_matched": case_metadata.get("adjacent_keywords_matched", []),
                "category": case_metadata.get("category", "other"),
            }
        )

    def _extract_case_reference(self, pdf_path: Path) -> str:
        """Extract case reference from file path."""
        # Path structure: .../year/case_reference/decision.pdf
        # or just use the parent directory name
        parent_name = pdf_path.parent.name
        if parent_name == "decision":
            # Go up one more level
            parent_name = pdf_path.parent.parent.name

        # Clean up the reference
        ref = parent_name.replace(".pdf", "").replace(".html", "")
        return ref

    def _extract_year(self, pdf_path: Path) -> int:
        """Extract year from file path."""
        # Look for year in path components
        year_pattern = re.compile(r"20[0-2][0-9]")

        for part in pdf_path.parts:
            match = year_pattern.search(part)
            if match:
                return int(match.group())

        # Default to current year if not found
        from datetime import datetime
        return datetime.now().year

    def get_stats(self) -> dict:
        """Get extraction statistics."""
        return self.extraction_stats.copy()

    def reset_stats(self) -> None:
        """Reset extraction statistics."""
        self.extraction_stats = {
            "total_processed": 0,
            "successful": 0,
            "failed": 0,
            "empty_content": 0,
        }


def extract_text_from_pdf(pdf_path: Path) -> str:
    """
    Convenience function to extract text from a PDF.

    Args:
        pdf_path: Path to PDF file

    Returns:
        Extracted text content
    """
    extractor = PDFExtractor()
    text, _ = extractor.extract_from_pdf(pdf_path)
    return text
