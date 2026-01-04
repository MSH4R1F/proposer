"""
Evidence processor for handling file uploads.

Extracts text from PDFs and describes images for evidence items.
"""

from pathlib import Path
from typing import Any, Dict, Optional

import structlog

from ..clients.base import BaseLLMClient
from ..models.case_file import EvidenceItem, EvidenceType

logger = structlog.get_logger()


class EvidenceProcessor:
    """
    Processes uploaded evidence files.

    Handles:
    - PDF text extraction
    - Image description using vision models
    - Evidence classification
    """

    def __init__(
        self,
        llm_client: Optional[BaseLLMClient] = None,
        pdf_extractor: Optional[Any] = None,
    ):
        """
        Initialize the evidence processor.

        Args:
            llm_client: LLM client for image description
            pdf_extractor: PDF extractor (from rag_engine if available)
        """
        self.llm = llm_client
        self.pdf_extractor = pdf_extractor

    async def process(
        self,
        file_path: str,
        file_type: str,
        evidence_type: Optional[EvidenceType] = None,
        description: str = "",
    ) -> EvidenceItem:
        """
        Process an evidence file.

        Args:
            file_path: Path or URL to the file
            file_type: MIME type of the file
            evidence_type: Type of evidence (if known)
            description: User-provided description

        Returns:
            EvidenceItem with extracted content
        """
        extracted_text = None
        image_description = None

        # Process based on file type
        if file_type == "application/pdf":
            extracted_text = await self._extract_pdf_text(file_path)
        elif file_type.startswith("image/"):
            image_description = await self._describe_image(file_path, description)

        # Infer evidence type if not provided
        if not evidence_type:
            evidence_type = self._infer_evidence_type(
                file_path, extracted_text, description
            )

        return EvidenceItem(
            type=evidence_type,
            description=description or self._generate_description(
                evidence_type, extracted_text, image_description
            ),
            file_url=file_path,
            file_type=file_type,
            extracted_text=extracted_text,
            image_description=image_description,
            source="uploaded",
        )

    async def _extract_pdf_text(self, file_path: str) -> Optional[str]:
        """Extract text from a PDF file."""
        if self.pdf_extractor:
            try:
                return self.pdf_extractor.extract(file_path)
            except Exception as e:
                logger.error("pdf_extraction_failed", error=str(e))

        # Fallback: try PyMuPDF directly
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(file_path)
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()

            return text.strip() if text.strip() else None

        except Exception as e:
            logger.error("pdf_fallback_extraction_failed", error=str(e))
            return None

    async def _describe_image(
        self, file_path: str, context: str = ""
    ) -> Optional[str]:
        """Generate description of an image using vision model."""
        if not self.llm:
            return None

        # Note: This would require vision capabilities
        # For now, return a placeholder
        logger.info("image_description_requested", file_path=file_path)

        # In production, this would use Claude's vision capabilities
        return f"Image evidence: {context}" if context else "Image evidence uploaded"

    def _infer_evidence_type(
        self,
        file_path: str,
        extracted_text: Optional[str],
        description: str,
    ) -> EvidenceType:
        """Infer evidence type from file name and content."""
        file_lower = file_path.lower()
        desc_lower = description.lower()
        text_lower = (extracted_text or "").lower()

        combined = f"{file_lower} {desc_lower} {text_lower}"

        # Check for inventory
        if any(word in combined for word in ["inventory", "check-in", "checkin"]):
            if any(word in combined for word in ["out", "checkout", "check-out", "end"]):
                return EvidenceType.INVENTORY_CHECKOUT
            return EvidenceType.INVENTORY_CHECKIN

        # Check for photos
        if any(word in combined for word in ["photo", "picture", "image"]):
            if any(word in combined for word in ["before", "start", "move in", "movein"]):
                return EvidenceType.PHOTOS_BEFORE
            return EvidenceType.PHOTOS_AFTER

        # Check for financial documents
        if any(word in combined for word in ["receipt", "paid"]):
            return EvidenceType.RECEIPTS
        if any(word in combined for word in ["invoice", "bill", "quote"]):
            return EvidenceType.INVOICES

        # Check for correspondence
        if any(word in combined for word in ["email", "letter", "message", "correspondence"]):
            return EvidenceType.CORRESPONDENCE

        # Check for tenancy documents
        if any(word in combined for word in ["tenancy", "agreement", "contract", "lease"]):
            return EvidenceType.TENANCY_AGREEMENT
        if any(word in combined for word in ["deposit", "certificate", "protection"]):
            return EvidenceType.DEPOSIT_CERTIFICATE

        return EvidenceType.OTHER

    def _generate_description(
        self,
        evidence_type: EvidenceType,
        extracted_text: Optional[str],
        image_description: Optional[str],
    ) -> str:
        """Generate a description for evidence without user description."""
        type_descriptions = {
            EvidenceType.INVENTORY_CHECKIN: "Check-in inventory document",
            EvidenceType.INVENTORY_CHECKOUT: "Check-out inventory document",
            EvidenceType.PHOTOS_BEFORE: "Photos of property condition at start",
            EvidenceType.PHOTOS_AFTER: "Photos of property condition at end",
            EvidenceType.RECEIPTS: "Receipt for payment",
            EvidenceType.INVOICES: "Invoice document",
            EvidenceType.CORRESPONDENCE: "Correspondence record",
            EvidenceType.TENANCY_AGREEMENT: "Tenancy agreement document",
            EvidenceType.DEPOSIT_CERTIFICATE: "Deposit protection certificate",
            EvidenceType.WITNESS_STATEMENT: "Witness statement",
            EvidenceType.OTHER: "Supporting document",
        }

        base_desc = type_descriptions.get(evidence_type, "Evidence document")

        if extracted_text:
            # Add a snippet of the extracted text
            snippet = extracted_text[:100].replace("\n", " ").strip()
            return f"{base_desc} - {snippet}..."

        if image_description:
            return f"{base_desc} - {image_description}"

        return base_desc
