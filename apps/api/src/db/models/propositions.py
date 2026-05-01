"""ORM rows for the Proposition Knowledge Graph (SHA-36).

Decision-derived atomic legal propositions and their typed edges. Distinct from
the intake-derived typed KG in `kg`. Four tables here:

- decision_documents          — one row per ingested tribunal decision document
- proposition_extraction_runs — one row per (document, extractor, prompt, model)
- propositions                — atomic legal claims extracted from a document
- proposition_edges           — typed links between two propositions

All UUID PKs are application-supplied (deterministic where possible — see
`kg_builder.propositions.deterministic_*`). Migration creating these tables
lives in Task 3.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from typing import Any, Optional

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import text as _sql_text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.src.db.base import Base
from apps.api.src.db.models._enums import (
    proposition_edge_type_enum,
    proposition_run_status_enum,
    proposition_type_enum,
)


class DecisionDocumentRow(Base):
    """One ingested tribunal decision document. Identified by content hash."""

    __tablename__ = "decision_documents"

    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    case_reference: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    local_path: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    case_type_code: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    region_code: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    decision_date: Mapped[Optional[_dt.date]] = mapped_column(Date, nullable=True)
    content_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    extraction_method: Mapped[str] = mapped_column(String(32), nullable=False)
    # `metadata` is reserved by SQLAlchemy's DeclarativeBase, so the Python
    # attribute is `metadata_` while the actual DB column is named `metadata`.
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=_sql_text("'{}'::jsonb"),
    )
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "char_count >= 0",
            name="ck_decision_documents_char_count_nonneg",
        ),
        CheckConstraint(
            "page_count IS NULL OR page_count >= 0",
            name="ck_decision_documents_page_count_nonneg",
        ),
    )


class PropositionExtractionRunRow(Base):
    """One extractor invocation against one document.

    Uniqueness is over (document, extractor_version, prompt_sha256, model) so
    re-running an identical pipeline against the same document is a no-op.
    """

    __tablename__ = "proposition_extraction_runs"

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("decision_documents.document_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(proposition_run_status_enum, nullable=False)
    input_chars: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False)
    proposition_count: Mapped[int] = mapped_column(Integer, nullable=False)
    edge_count: Mapped[int] = mapped_column(Integer, nullable=False)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False)
    tokens_in: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Note: no UniqueConstraint on (document_id, extractor_version, prompt_sha256,
    # model) — Phase 1 Task 9 dropped it. The CLI's --resume / --force flags
    # enforce dedup at the application layer; the DB allows multiple succeeded
    # runs of the same pipeline against the same document so deliberate
    # re-runs (e.g. measurement / variance studies) are not blocked.
    __table_args__ = (
        CheckConstraint(
            "input_chars >= 0",
            name="ck_proposition_runs_input_chars_nonneg",
        ),
        CheckConstraint(
            "chunk_count >= 0",
            name="ck_proposition_runs_chunk_count_nonneg",
        ),
        CheckConstraint(
            "proposition_count >= 0",
            name="ck_proposition_runs_proposition_count_nonneg",
        ),
        CheckConstraint(
            "edge_count >= 0",
            name="ck_proposition_runs_edge_count_nonneg",
        ),
        CheckConstraint(
            "rejected_count >= 0",
            name="ck_proposition_runs_rejected_count_nonneg",
        ),
        CheckConstraint(
            "tokens_in IS NULL OR tokens_in >= 0",
            name="ck_proposition_runs_tokens_in_nonneg",
        ),
        CheckConstraint(
            "tokens_out IS NULL OR tokens_out >= 0",
            name="ck_proposition_runs_tokens_out_nonneg",
        ),
    )


class PropositionRow(Base):
    """An atomic legal proposition extracted from a single decision document."""

    __tablename__ = "propositions"

    proposition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("decision_documents.document_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("proposition_extraction_runs.run_id", ondelete="SET NULL"),
        nullable=True,
    )
    case_reference: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    source_passage: Mapped[str] = mapped_column(String(1500), nullable=False)
    paragraph_ref: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source_start_char: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_end_char: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    page_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    page_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    proposition_type: Mapped[str] = mapped_column(
        proposition_type_enum, nullable=False
    )
    issue_tags: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=_sql_text("'[]'::jsonb")
    )
    entities: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=_sql_text("'[]'::jsonb")
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_propositions_confidence_range",
        ),
        CheckConstraint(
            "source_start_char IS NULL OR source_start_char >= 0",
            name="ck_propositions_source_start_char_nonneg",
        ),
        CheckConstraint(
            "source_end_char IS NULL OR ("
            "source_start_char IS NOT NULL AND source_end_char >= source_start_char"
            ")",
            name="ck_propositions_source_end_char_after_start",
        ),
        CheckConstraint(
            "page_start IS NULL OR page_start >= 1",
            name="ck_propositions_page_start_positive",
        ),
        CheckConstraint(
            "page_end IS NULL OR ("
            "page_start IS NOT NULL AND page_end >= page_start"
            ")",
            name="ck_propositions_page_end_after_start",
        ),
        Index("ix_propositions_case_reference", "case_reference"),
        Index("ix_propositions_document_type", "document_id", "proposition_type"),
        Index("ix_propositions_paragraph_ref", "paragraph_ref"),
        Index(
            "ix_propositions_issue_tags_gin",
            "issue_tags",
            postgresql_using="gin",
        ),
        Index(
            "ix_propositions_entities_gin",
            "entities",
            postgresql_using="gin",
        ),
    )


class PropositionEdgeRow(Base):
    """A typed directed link between two propositions in the same document."""

    __tablename__ = "proposition_edges"

    edge_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    from_proposition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("propositions.proposition_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    to_proposition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("propositions.proposition_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("decision_documents.document_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    edge_type: Mapped[str] = mapped_column(proposition_edge_type_enum, nullable=False)
    rationale: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "from_proposition_id",
            "to_proposition_id",
            "edge_type",
            name="uq_proposition_edges_triple",
        ),
        CheckConstraint(
            "from_proposition_id <> to_proposition_id",
            name="ck_proposition_edges_no_self_loop",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_proposition_edges_confidence_range",
        ),
    )
