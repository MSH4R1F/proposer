"""Proposition KG subpackage (SHA-36).

Decision-derived atomic legal propositions and their typed edges. Distinct
from the intake-derived typed KG in `kg_builder.builders` — different
ontology, different lifecycle, different storage.
"""

from .models import (
    DecisionDocument,
    ExtractionRunStatus,
    Proposition,
    PropositionEdge,
    PropositionEdgeType,
    PropositionExtractionRun,
    PropositionType,
    deterministic_document_id,
    deterministic_edge_id,
    deterministic_proposition_id,
    normalize_for_matching,
    sha256_hex,
)

__all__ = [
    "DecisionDocument",
    "ExtractionRunStatus",
    "Proposition",
    "PropositionEdge",
    "PropositionEdgeType",
    "PropositionExtractionRun",
    "PropositionType",
    "deterministic_document_id",
    "deterministic_edge_id",
    "deterministic_proposition_id",
    "normalize_for_matching",
    "sha256_hex",
]
