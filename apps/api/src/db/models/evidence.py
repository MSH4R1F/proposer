from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import Index, String, Text
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
    storage_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # SHA-124 phase 2: domain id + structured source provenance.
    # ``domain_id``/``domain_version`` are NOT NULL after revision 0003.
    # ``source_*`` stay nullable until the corpus pipeline tags evidence
    # with a structured source reference (Phase 4 of the SHA-20 plan).
    domain_id: Mapped[str] = mapped_column(
        Text, nullable=False, default="housing.deposit.v1",
        server_default="housing.deposit.v1",
    )
    domain_version: Mapped[str] = mapped_column(
        Text, nullable=False, default="v1", server_default="v1",
    )
    source_kind: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_publisher: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_evidence_metadata_domain_source_kind", "domain_id", "source_kind"),
    )
