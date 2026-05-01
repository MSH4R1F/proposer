"""Tighten domain metadata to NOT NULL once application code writes it.

This is the second half of the SHA-124 zero-downtime migration. After
revision ``0002`` is deployed and application code is consistently writing
``domain_id`` / ``domain_version`` / ``matter_types`` / ``routing_metadata``
on every insert, this revision flips those columns to NOT NULL.

What stays nullable forever (per Phase 0 audit + Phase 2 plan):
- ``forum`` on disputes/predictions (audit finding #2: deposit corpus on
  disk does not cleanly identify a forum).
- ``routing_confidence`` (only set when routing actually inferred a domain).
- The four reproducibility hashes (only set on rows produced after the
  domain spec/prompt pack/ontology/corpus pipeline is wired in).
- ``source_*`` columns on evidence_metadata + prediction_citations (only
  set once the corpus + citation pipeline emits structured provenance).
- ``namespace_id`` / ``canonical_url`` / ``source_license`` on
  prediction_citations.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-01
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


# (table, column) pairs we want NOT NULL from this revision onward.
_NOT_NULL_COLUMNS = (
    ("intake_sessions",     "domain_id"),
    ("intake_sessions",     "domain_version"),
    ("intake_sessions",     "matter_types"),
    ("intake_sessions",     "routing_metadata"),

    ("disputes",            "domain_id"),
    ("disputes",            "domain_version"),
    ("disputes",            "matter_types"),
    ("disputes",            "routing_metadata"),

    ("predictions",         "domain_id"),
    ("predictions",         "domain_version"),
    ("predictions",         "matter_types"),
    ("predictions",         "routing_metadata"),

    ("knowledge_graphs",    "domain_id"),
    ("knowledge_graphs",    "domain_version"),

    ("mediations",          "domain_id"),
    ("mediations",          "domain_version"),

    ("evidence_metadata",   "domain_id"),
    ("evidence_metadata",   "domain_version"),

    ("prediction_citations", "domain_id"),
)


def upgrade() -> None:
    for table, column in _NOT_NULL_COLUMNS:
        op.alter_column(table, column, nullable=False)


def downgrade() -> None:
    for table, column in reversed(_NOT_NULL_COLUMNS):
        op.alter_column(table, column, nullable=True)
