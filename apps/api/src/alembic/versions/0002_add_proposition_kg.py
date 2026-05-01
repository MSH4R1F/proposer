"""add proposition KG (decision documents, propositions, edges, extraction runs)

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-01

Introduces the decision-derived Proposition Knowledge Graph (SHA-36):
  - decision_documents          : ingested tribunal decisions
  - proposition_extraction_runs : one row per (document, extractor, prompt, model)
  - propositions                : atomic legal claims extracted from documents
  - proposition_edges           : typed directed links between propositions

Schema mirrors the ORM in apps/api/src/db/models/propositions.py exactly. This
migration is the source of truth for production schema.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM, JSONB, UUID

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


# Enum names + values — must match _enums.py exactly.
ENUMS: dict[str, tuple[str, ...]] = {
    "proposition_type": ("fact", "rule", "outcome", "authority"),
    "proposition_edge_type": (
        "supports",
        "contradicts",
        "cites",
        "temporal_before",
        "applies_rule_to_fact",
    ),
    "proposition_run_status": ("started", "succeeded", "failed", "skipped"),
}


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Create enum types BEFORE any table that references them.
    #    checkfirst=True so a re-run after a partial failure still works.
    for name, values in ENUMS.items():
        sa.Enum(*values, name=name).create(bind, checkfirst=True)

    # 2. decision_documents — root of the proposition graph.
    op.create_table(
        "decision_documents",
        sa.Column("document_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("case_reference", sa.String(128), nullable=False),
        sa.Column("source_url", sa.String(2048), nullable=True),
        sa.Column("local_path", sa.String(2048), nullable=True),
        sa.Column("year", sa.Integer, nullable=True),
        sa.Column("category", sa.String(32), nullable=True),
        sa.Column("case_type_code", sa.String(16), nullable=True),
        sa.Column("region_code", sa.String(16), nullable=True),
        sa.Column("decision_date", sa.Date, nullable=True),
        sa.Column("content_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("text_sha256", sa.String(64), nullable=False),
        sa.Column("char_count", sa.Integer, nullable=False),
        sa.Column("page_count", sa.Integer, nullable=True),
        sa.Column("extraction_method", sa.String(32), nullable=False),
        # `metadata` collides with SQLAlchemy's DeclarativeBase attribute, but
        # the DB column itself is named `metadata`.
        sa.Column(
            "metadata",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "char_count >= 0",
            name="ck_decision_documents_char_count_nonneg",
        ),
        sa.CheckConstraint(
            "page_count IS NULL OR page_count >= 0",
            name="ck_decision_documents_page_count_nonneg",
        ),
    )
    op.create_index(
        "ix_decision_documents_case_reference",
        "decision_documents",
        ["case_reference"],
    )

    # 3. proposition_extraction_runs — depends on decision_documents.
    op.create_table(
        "proposition_extraction_runs",
        sa.Column("run_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("decision_documents.document_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("extractor_version", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("prompt_sha256", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column(
            "status",
            PG_ENUM(name="proposition_run_status", create_type=False),
            nullable=False,
        ),
        sa.Column("input_chars", sa.Integer, nullable=False),
        sa.Column("chunk_count", sa.Integer, nullable=False),
        sa.Column("proposition_count", sa.Integer, nullable=False),
        sa.Column("edge_count", sa.Integer, nullable=False),
        sa.Column("rejected_count", sa.Integer, nullable=False),
        sa.Column("tokens_in", sa.Integer, nullable=True),
        sa.Column("tokens_out", sa.Integer, nullable=True),
        sa.Column("error_message", sa.String(2000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "document_id",
            "extractor_version",
            "prompt_sha256",
            "model",
            name="uq_proposition_runs_document_extractor",
        ),
        sa.CheckConstraint(
            "input_chars >= 0",
            name="ck_proposition_runs_input_chars_nonneg",
        ),
        sa.CheckConstraint(
            "chunk_count >= 0",
            name="ck_proposition_runs_chunk_count_nonneg",
        ),
        sa.CheckConstraint(
            "proposition_count >= 0",
            name="ck_proposition_runs_proposition_count_nonneg",
        ),
        sa.CheckConstraint(
            "edge_count >= 0",
            name="ck_proposition_runs_edge_count_nonneg",
        ),
        sa.CheckConstraint(
            "rejected_count >= 0",
            name="ck_proposition_runs_rejected_count_nonneg",
        ),
        sa.CheckConstraint(
            "tokens_in IS NULL OR tokens_in >= 0",
            name="ck_proposition_runs_tokens_in_nonneg",
        ),
        sa.CheckConstraint(
            "tokens_out IS NULL OR tokens_out >= 0",
            name="ck_proposition_runs_tokens_out_nonneg",
        ),
    )
    op.create_index(
        "ix_proposition_extraction_runs_document_id",
        "proposition_extraction_runs",
        ["document_id"],
    )

    # 4. propositions — depends on decision_documents and (nullable) runs.
    #    run_id FK uses SET NULL (not CASCADE) so deleting a run for retraceability
    #    purposes does not lose the propositions it produced.
    op.create_table(
        "propositions",
        sa.Column("proposition_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("decision_documents.document_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey(
                "proposition_extraction_runs.run_id", ondelete="SET NULL"
            ),
            nullable=True,
        ),
        sa.Column("case_reference", sa.String(128), nullable=False),
        sa.Column("text", sa.String(500), nullable=False),
        sa.Column("source_passage", sa.String(1500), nullable=False),
        sa.Column("paragraph_ref", sa.String(64), nullable=True),
        sa.Column("source_start_char", sa.Integer, nullable=True),
        sa.Column("source_end_char", sa.Integer, nullable=True),
        sa.Column("page_start", sa.Integer, nullable=True),
        sa.Column("page_end", sa.Integer, nullable=True),
        sa.Column(
            "proposition_type",
            PG_ENUM(name="proposition_type", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "issue_tags",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "entities",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_propositions_confidence_range",
        ),
        sa.CheckConstraint(
            "source_start_char IS NULL OR source_start_char >= 0",
            name="ck_propositions_source_start_char_nonneg",
        ),
        sa.CheckConstraint(
            "source_end_char IS NULL OR ("
            "source_start_char IS NOT NULL AND source_end_char >= source_start_char"
            ")",
            name="ck_propositions_source_end_char_after_start",
        ),
        sa.CheckConstraint(
            "page_start IS NULL OR page_start >= 1",
            name="ck_propositions_page_start_positive",
        ),
        sa.CheckConstraint(
            "page_end IS NULL OR ("
            "page_start IS NOT NULL AND page_end >= page_start"
            ")",
            name="ck_propositions_page_end_after_start",
        ),
    )
    op.create_index("ix_propositions_document_id", "propositions", ["document_id"])
    op.create_index(
        "ix_propositions_case_reference", "propositions", ["case_reference"]
    )
    op.create_index(
        "ix_propositions_document_type",
        "propositions",
        ["document_id", "proposition_type"],
    )
    op.create_index(
        "ix_propositions_paragraph_ref", "propositions", ["paragraph_ref"]
    )
    op.create_index(
        "ix_propositions_issue_tags_gin",
        "propositions",
        ["issue_tags"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_propositions_entities_gin",
        "propositions",
        ["entities"],
        postgresql_using="gin",
    )

    # 5. proposition_edges — depends on propositions and decision_documents.
    op.create_table(
        "proposition_edges",
        sa.Column("edge_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "from_proposition_id",
            UUID(as_uuid=True),
            sa.ForeignKey("propositions.proposition_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "to_proposition_id",
            UUID(as_uuid=True),
            sa.ForeignKey("propositions.proposition_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("decision_documents.document_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "edge_type",
            PG_ENUM(name="proposition_edge_type", create_type=False),
            nullable=False,
        ),
        sa.Column("rationale", sa.String(500), nullable=True),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "from_proposition_id",
            "to_proposition_id",
            "edge_type",
            name="uq_proposition_edges_triple",
        ),
        sa.CheckConstraint(
            "from_proposition_id <> to_proposition_id",
            name="ck_proposition_edges_no_self_loop",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_proposition_edges_confidence_range",
        ),
    )
    op.create_index(
        "ix_proposition_edges_from_proposition_id",
        "proposition_edges",
        ["from_proposition_id"],
    )
    op.create_index(
        "ix_proposition_edges_to_proposition_id",
        "proposition_edges",
        ["to_proposition_id"],
    )
    op.create_index(
        "ix_proposition_edges_document_id",
        "proposition_edges",
        ["document_id"],
    )


def downgrade() -> None:
    # Drop tables in reverse dependency order.
    op.drop_table("proposition_edges")
    op.drop_table("propositions")
    op.drop_table("proposition_extraction_runs")
    op.drop_table("decision_documents")

    # Drop enums AFTER tables (dependent objects must be gone first).
    bind = op.get_bind()
    for name in reversed(list(ENUMS.keys())):
        sa.Enum(name=name).drop(bind, checkfirst=True)
