"""Add housing-repairs values to the ``issue_type`` enum.

The canonical Python enum
(``llm_orchestrator.models.case_file.DisputeIssue``) gained
``repairs_disrepair`` / ``repairs_damp_mould`` / ``complaint_handling_failure``
for the housing-repairs domain, but the Postgres ``issue_type`` enum (created in
revision 0001) was never extended. Persisting a dispute with one of these issue
types therefore failed with ``invalid input value for enum issue_type``. This
migration adds the missing labels so the DB matches the canonical enum.

``ALTER TYPE ... ADD VALUE`` cannot run inside the migration's normal
transaction on all Postgres versions, so we use Alembic's ``autocommit_block``.
``IF NOT EXISTS`` keeps the upgrade idempotent.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-30
"""

from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

_NEW_VALUES = (
    "repairs_disrepair",
    "repairs_damp_mould",
    "complaint_handling_failure",
)


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for value in _NEW_VALUES:
            op.execute(f"ALTER TYPE issue_type ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # Postgres cannot remove a value from an enum type, so this is a no-op.
    # Dropping the values would require recreating the enum and rewriting every
    # dependent column, which is unsafe to do automatically.
    pass
