"""Evidence metadata domain model."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class EvidenceMetadata(BaseModel):
    """Metadata for a single piece of evidence attached to a case."""

    case_id: str
    evidence_id: str
    evidence_type: str  # one of EvidenceType enum values
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    file_type: Optional[str] = None
    description: Optional[str] = None
    extracted_text: Optional[str] = None
    image_description: Optional[str] = None
    created_at: Optional[str] = None
