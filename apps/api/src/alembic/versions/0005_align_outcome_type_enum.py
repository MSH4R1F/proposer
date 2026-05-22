"""Align the ``outcome_type`` enum with the pipeline + ``issue_outcome``.

The prediction pipeline (``llm_orchestrator.models.prediction_v2.OutcomeType``)
emits plural outcome strings — ``tenant_wins`` / ``landlord_wins`` — and the
sibling ``issue_outcome`` enum already uses the plural form. Only
``outcome_type`` was created with the singular ``tenant_win`` / ``landlord_win``
(revision 0001), so persisting any decisive overall prediction failed with
``invalid input value for enum outcome_type: "tenant_wins"`` and 500'd the
``POST /predictions/generate`` endpoint.

``ALTER TYPE ... RENAME VALUE`` (Postgres 10+) renames the label in place and
rewrites every existing row that used it, so the handful of legacy
``tenant_win`` rows are migrated to ``tenant_wins`` automatically.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-22
"""

from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

# (old singular label, new plural label) for the outcome_type enum.
_RENAMES = (
    ("tenant_win", "tenant_wins"),
    ("landlord_win", "landlord_wins"),
)


def upgrade() -> None:
    for old, new in _RENAMES:
        op.execute(f"ALTER TYPE outcome_type RENAME VALUE '{old}' TO '{new}'")


def downgrade() -> None:
    for old, new in _RENAMES:
        op.execute(f"ALTER TYPE outcome_type RENAME VALUE '{new}' TO '{old}'")
