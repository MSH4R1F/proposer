"""Add nullable domain metadata + provenance columns (SHA-124 phase 2a).

Adds domain routing and reproducibility columns as nullable, then backfills
existing rows to ``housing.deposit.v1`` (D1 of the Phase 0 audit). Indexes are
created here so the metadata is queryable as soon as it is written.

A follow-up revision (``0004_domain_metadata_not_null``) tightens the columns
that must be NOT NULL once application code is deployed and writing them.

Chains after ``0002_add_proposition_kg`` (SHA-36 Phase 2). The proposition KG
tables are independent of the domain metadata columns, so the order is
purely chronological.

Notes:
- Uses TEXT/JSONB columns rather than Postgres ENUMs for ``domain_id``,
  ``forum``, ``source_kind``, and ``source_publisher``. The registry will
  change faster than DB enum migrations can ship.
- ``forum`` is left NULL after backfill — the Phase 0 audit explicitly notes
  the deposit corpus on disk does not cleanly identify a forum.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


# Tables that participate in domain routing AND/OR reproducibility.
# Routing-only tables get the lightweight 5-column block.
# Reproducibility tables get the four hashes too.
# Source-of-truth provenance columns live on evidence_metadata + prediction_citations.


def _add_routing_columns(table: str) -> None:
    op.add_column(table, sa.Column("domain_id", sa.Text(), nullable=True))
    op.add_column(table, sa.Column("domain_version", sa.Text(), nullable=True))
    op.add_column(table, sa.Column("matter_types", JSONB, nullable=True))
    op.add_column(table, sa.Column("routing_confidence", sa.Numeric(), nullable=True))
    op.add_column(table, sa.Column("routing_metadata", JSONB, nullable=True))


def _add_repro_columns(table: str) -> None:
    op.add_column(table, sa.Column("domain_spec_hash", sa.Text(), nullable=True))
    op.add_column(table, sa.Column("prompt_pack_hash", sa.Text(), nullable=True))
    op.add_column(table, sa.Column("ontology_hash", sa.Text(), nullable=True))
    op.add_column(table, sa.Column("corpus_version", sa.Text(), nullable=True))


def upgrade() -> None:
    # ----- intake_sessions: routing only -------------------------------------
    _add_routing_columns("intake_sessions")

    # ----- disputes: routing + forum -----------------------------------------
    _add_routing_columns("disputes")
    op.add_column("disputes", sa.Column("forum", sa.Text(), nullable=True))

    # ----- predictions: routing + forum + reproducibility hashes -------------
    _add_routing_columns("predictions")
    op.add_column("predictions", sa.Column("forum", sa.Text(), nullable=True))
    _add_repro_columns("predictions")

    # ----- knowledge_graphs: domain id + ontology hashes ---------------------
    op.add_column("knowledge_graphs", sa.Column("domain_id", sa.Text(), nullable=True))
    op.add_column("knowledge_graphs", sa.Column("domain_version", sa.Text(), nullable=True))
    op.add_column("knowledge_graphs", sa.Column("domain_spec_hash", sa.Text(), nullable=True))
    op.add_column("knowledge_graphs", sa.Column("ontology_hash", sa.Text(), nullable=True))

    # ----- mediations: domain id only ----------------------------------------
    op.add_column("mediations", sa.Column("domain_id", sa.Text(), nullable=True))
    op.add_column("mediations", sa.Column("domain_version", sa.Text(), nullable=True))

    # ----- evidence_metadata: domain id + source provenance ------------------
    op.add_column("evidence_metadata", sa.Column("domain_id", sa.Text(), nullable=True))
    op.add_column("evidence_metadata", sa.Column("domain_version", sa.Text(), nullable=True))
    op.add_column("evidence_metadata", sa.Column("source_kind", sa.Text(), nullable=True))
    op.add_column("evidence_metadata", sa.Column("source_publisher", sa.Text(), nullable=True))
    op.add_column("evidence_metadata", sa.Column("source_id", sa.Text(), nullable=True))

    # ----- prediction_citations: domain id + full source provenance ----------
    op.add_column("prediction_citations", sa.Column("domain_id", sa.Text(), nullable=True))
    op.add_column("prediction_citations", sa.Column("source_kind", sa.Text(), nullable=True))
    op.add_column("prediction_citations", sa.Column("source_publisher", sa.Text(), nullable=True))
    op.add_column("prediction_citations", sa.Column("source_id", sa.Text(), nullable=True))
    op.add_column("prediction_citations", sa.Column("namespace_id", sa.Text(), nullable=True))
    op.add_column("prediction_citations", sa.Column("canonical_url", sa.Text(), nullable=True))
    op.add_column("prediction_citations", sa.Column("source_license", sa.Text(), nullable=True))

    # ----- backfill ----------------------------------------------------------
    # D1: housing.deposit.v1 is the compatibility default.
    # forum is intentionally NOT backfilled (Phase 0 audit, finding #2).
    bind = op.get_bind()
    routing_tables = (
        "intake_sessions",
        "disputes",
        "predictions",
        "knowledge_graphs",
        "mediations",
        "evidence_metadata",
        "prediction_citations",
    )
    for tbl in routing_tables:
        bind.execute(sa.text(
            f"UPDATE {tbl} SET domain_id = 'housing.deposit.v1' WHERE domain_id IS NULL"
        ))
    # domain_version exists on every routing table.
    for tbl in routing_tables:
        # prediction_citations does not carry domain_version (only domain_id).
        if tbl == "prediction_citations":
            continue
        bind.execute(sa.text(
            f"UPDATE {tbl} SET domain_version = 'v1' WHERE domain_version IS NULL"
        ))
    # matter_types and routing_metadata exist only on the routing-block tables.
    for tbl in ("intake_sessions", "disputes", "predictions"):
        bind.execute(sa.text(
            f"UPDATE {tbl} SET matter_types = '[]'::jsonb WHERE matter_types IS NULL"
        ))
        bind.execute(sa.text(
            f"UPDATE {tbl} SET routing_metadata = '{{}}'::jsonb WHERE routing_metadata IS NULL"
        ))

    # ----- server-side defaults so future inserts that omit the column ------
    # ----- still get a sensible value -------------------------------------
    for tbl in routing_tables:
        op.alter_column(tbl, "domain_id",
                        server_default=sa.text("'housing.deposit.v1'"))
    for tbl in routing_tables:
        if tbl == "prediction_citations":
            continue
        op.alter_column(tbl, "domain_version", server_default=sa.text("'v1'"))
    for tbl in ("intake_sessions", "disputes", "predictions"):
        op.alter_column(tbl, "matter_types",
                        server_default=sa.text("'[]'::jsonb"))
        op.alter_column(tbl, "routing_metadata",
                        server_default=sa.text("'{}'::jsonb"))

    # ----- indexes -----------------------------------------------------------
    op.create_index(
        "ix_predictions_domain_created_at",
        "predictions",
        ["domain_id", "created_at"],
    )
    op.create_index(
        "ix_disputes_domain_forum",
        "disputes",
        ["domain_id", "forum"],
    )
    op.create_index(
        "ix_evidence_metadata_domain_source_kind",
        "evidence_metadata",
        ["domain_id", "source_kind"],
    )
    op.create_index(
        "ix_prediction_citations_source_id",
        "prediction_citations",
        ["source_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_prediction_citations_source_id", table_name="prediction_citations")
    op.drop_index("ix_evidence_metadata_domain_source_kind", table_name="evidence_metadata")
    op.drop_index("ix_disputes_domain_forum", table_name="disputes")
    op.drop_index("ix_predictions_domain_created_at", table_name="predictions")

    # prediction_citations
    for col in (
        "source_license", "canonical_url", "namespace_id",
        "source_id", "source_publisher", "source_kind", "domain_id",
    ):
        op.drop_column("prediction_citations", col)

    # evidence_metadata
    for col in (
        "source_id", "source_publisher", "source_kind",
        "domain_version", "domain_id",
    ):
        op.drop_column("evidence_metadata", col)

    # mediations
    for col in ("domain_version", "domain_id"):
        op.drop_column("mediations", col)

    # knowledge_graphs
    for col in ("ontology_hash", "domain_spec_hash", "domain_version", "domain_id"):
        op.drop_column("knowledge_graphs", col)

    # predictions: drop reproducibility hashes, forum, then routing columns
    for col in ("corpus_version", "ontology_hash", "prompt_pack_hash", "domain_spec_hash"):
        op.drop_column("predictions", col)
    op.drop_column("predictions", "forum")
    for col in ("routing_metadata", "routing_confidence", "matter_types",
                "domain_version", "domain_id"):
        op.drop_column("predictions", col)

    # disputes
    op.drop_column("disputes", "forum")
    for col in ("routing_metadata", "routing_confidence", "matter_types",
                "domain_version", "domain_id"):
        op.drop_column("disputes", col)

    # intake_sessions
    for col in ("routing_metadata", "routing_confidence", "matter_types",
                "domain_version", "domain_id"):
        op.drop_column("intake_sessions", col)
