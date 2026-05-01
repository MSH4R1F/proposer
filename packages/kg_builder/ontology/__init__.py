"""KG ontology layer (SHA-61, SHA-119).

Provides per-domain ontology specs that constrain the node and edge kinds
allowed in a KnowledgeGraph. Loaded from YAML files in this directory and
validated at import time.

This sub-package MUST remain a leaf-ish module: it may import
``packages/domain_core`` for shared enums (Forum, SourceKind, etc.) but it
must NOT import ``rag_engine``, ``llm_orchestrator``, ``eval``, or any
``apps.*``. Cross-checked by ``tests/test_ontology_import_boundary.py``.
"""

from kg_builder.ontology.spec import (
    AllowedEdgeKind,
    AllowedNodeKind,
    OntologySpec,
)
from kg_builder.ontology.registry import (
    get_ontology,
    list_ontologies,
    load_ontology,
    reset_ontology_cache,
)
from kg_builder.ontology.validators import (
    OntologyValidationError,
    validate_graph_against_ontology,
)

__all__ = [
    "AllowedEdgeKind",
    "AllowedNodeKind",
    "OntologySpec",
    "OntologyValidationError",
    "get_ontology",
    "list_ontologies",
    "load_ontology",
    "reset_ontology_cache",
    "validate_graph_against_ontology",
]
