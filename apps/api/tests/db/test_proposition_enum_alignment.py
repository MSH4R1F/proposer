"""Asserts the 3 new Postgres enums match the Pydantic enums in kg_builder.propositions.

Pattern matches apps/api/tests/db/test_enum_alignment.py.
"""

from kg_builder.propositions import (
    ExtractionRunStatus,
    PropositionEdgeType,
    PropositionType,
)

from apps.api.src.db.models._enums import (
    proposition_edge_type_enum,
    proposition_run_status_enum,
    proposition_type_enum,
)


def test_proposition_type_enum_matches_pydantic() -> None:
    assert set(proposition_type_enum.enums) == {t.value for t in PropositionType}


def test_proposition_edge_type_enum_matches_pydantic() -> None:
    assert set(proposition_edge_type_enum.enums) == {
        t.value for t in PropositionEdgeType
    }


def test_proposition_run_status_enum_matches_pydantic() -> None:
    assert set(proposition_run_status_enum.enums) == {
        t.value for t in ExtractionRunStatus
    }
