from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.src.db.base import Base
from apps.api.src.db.models._enums import evidence_type_enum


class EvidenceMetadataRow(Base):
    __tablename__ = "evidence_metadata"

    case_id: Mapped[str] = mapped_column(String, primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String, primary_key=True)
    evidence_type: Mapped[str] = mapped_column(evidence_type_enum, nullable=False)
    file_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
