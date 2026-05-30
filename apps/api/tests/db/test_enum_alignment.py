"""Enum alignment between Postgres and canonical Python enums.

The conftest adds both the project root and packages/ to sys.path, so
llm_orchestrator and kg_builder are importable as top-level packages (not as
packages.llm_orchestrator / packages.kg_builder).

Citation source enum is intentionally skipped — Citation.source is `str` in
the Python model (packages/llm_orchestrator/models/prediction_v2.py). If a
CitationSource enum is introduced on the Python side, add the mapping here:
    (citation_source_enum, CitationSource)
"""

import pytest
from sqlalchemy import text

from apps.api.src.db.models._enums import (
    intake_stage_enum,
    dispute_status_enum,
    party_role_enum,
    user_role_enum,
    issue_type_enum,
    evidence_type_enum,
    evidence_strength_enum,
    outcome_type_enum,
    issue_outcome_enum,
    mediation_status_enum,
    offer_status_enum,
    message_type_enum,
    node_type_enum,
    edge_type_enum,
)
from llm_orchestrator.models.conversation import IntakeStage
from llm_orchestrator.models.dispute import DisputeStatus
from llm_orchestrator.models.case_file import PartyRole, DisputeIssue, EvidenceType
from llm_orchestrator.models.prediction_v2 import (
    OutcomeType,
    IssueOutcome,
    EvidenceStrength,
)
from llm_orchestrator.models.mediation import (
    MediationStatus,
    OfferStatus,
    MessageType,
)
from kg_builder.models.nodes import NodeType
from kg_builder.models.edges import EdgeType


PAIRS = [
    (intake_stage_enum, IntakeStage),
    (dispute_status_enum, DisputeStatus),
    (party_role_enum, PartyRole),
    (user_role_enum, PartyRole),
    (issue_type_enum, DisputeIssue),
    (evidence_type_enum, EvidenceType),
    (evidence_strength_enum, EvidenceStrength),
    (outcome_type_enum, OutcomeType),
    (issue_outcome_enum, IssueOutcome),
    (mediation_status_enum, MediationStatus),
    (offer_status_enum, OfferStatus),
    (message_type_enum, MessageType),
    (node_type_enum, NodeType),
    (edge_type_enum, EdgeType),
]


def _pair_id(val):
    """Return a readable pytest ID for a PG ENUM object or Python enum class."""
    if hasattr(val, "name"):
        # SQLAlchemy ENUM has .name (the PG type name)
        return val.name
    if hasattr(val, "__name__"):
        # Python enum class
        return val.__name__
    return str(val)


@pytest.mark.parametrize("pg_enum,py_enum", PAIRS, ids=_pair_id)
def test_pg_enum_values_match_python(pg_enum, py_enum) -> None:
    """Assert that every Postgres enum has the exact same value set as its
    canonical Python counterpart.  If this test fails a future commit has
    drifted one side without updating the other — fix the drift, do NOT
    silence the test."""
    pg_values = set(pg_enum.enums)
    py_values = {member.value for member in py_enum}
    assert pg_values == py_values, (
        f"Drift between PG enum {pg_enum.name!r} and Python {py_enum.__name__}: "
        f"only-in-PG={pg_values - py_values!r}, "
        f"only-in-Python={py_values - pg_values!r}"
    )


async def _live_enum_labels(db_session, type_name: str) -> set[str]:
    """Return the value set of a Postgres enum from the head-migrated DB.

    Reads the *effective* schema (every migration applied, not just 0001), so
    in-place enum changes like 0005's ``RENAME VALUE`` and 0006's ``ADD VALUE``
    are reflected automatically — and future enum migrations need no test edits.
    """
    result = await db_session.execute(
        text(
            "SELECT e.enumlabel "
            "FROM pg_enum e JOIN pg_type t ON e.enumtypid = t.oid "
            "WHERE t.typname = :type_name"
        ),
        {"type_name": type_name},
    )
    return {row[0] for row in result}


@pytest.mark.asyncio
@pytest.mark.parametrize("pg_enum,py_enum", PAIRS, ids=_pair_id)
async def test_migrated_db_enum_values_match_python(db_session, pg_enum, py_enum) -> None:
    """The enum in the fully-migrated DB must match its canonical Python enum.

    If this fails, a migration drifted the schema from the Python source of
    truth (or a Python enum changed without a migration) — fix the drift, do
    NOT silence the test."""
    db_values = await _live_enum_labels(db_session, pg_enum.name)
    py_values = {member.value for member in py_enum}
    assert db_values == py_values, (
        f"Drift between migrated DB enum {pg_enum.name!r} and Python "
        f"{py_enum.__name__}: only-in-DB={db_values - py_values!r}, "
        f"only-in-Python={py_values - db_values!r}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("pg_enum,_py_enum", PAIRS, ids=_pair_id)
async def test_migrated_db_enum_values_match_orm(db_session, pg_enum, _py_enum) -> None:
    """The enum in the fully-migrated DB must match the ORM ENUM definition."""
    db_values = await _live_enum_labels(db_session, pg_enum.name)
    assert db_values == set(pg_enum.enums), (
        f"Drift between migrated DB enum {pg_enum.name!r} and ORM definition: "
        f"only-in-DB={db_values - set(pg_enum.enums)!r}, "
        f"only-in-ORM={set(pg_enum.enums) - db_values!r}"
    )
