"""Enum alignment between Postgres and canonical Python enums.

The conftest adds both the project root and packages/ to sys.path, so
llm_orchestrator and kg_builder are importable as top-level packages (not as
packages.llm_orchestrator / packages.kg_builder).

Citation source enum is intentionally skipped — Citation.source is `str` in
the Python model (packages/llm_orchestrator/models/prediction_v2.py). If a
CitationSource enum is introduced on the Python side, add the mapping here:
    (citation_source_enum, CitationSource)
"""

import importlib

import pytest

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

initial_schema = importlib.import_module(
    "apps.api.src.alembic.versions.0001_initial_schema"
)


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


@pytest.mark.parametrize("pg_enum,py_enum", PAIRS, ids=_pair_id)
def test_migration_enum_values_match_python(pg_enum, py_enum) -> None:
    migration_values = set(initial_schema.ENUMS[pg_enum.name])
    py_values = {member.value for member in py_enum}
    assert migration_values == py_values


@pytest.mark.parametrize("pg_enum,_py_enum", PAIRS, ids=_pair_id)
def test_migration_enum_values_match_orm(pg_enum, _py_enum) -> None:
    assert set(initial_schema.ENUMS[pg_enum.name]) == set(pg_enum.enums)
