"""legal_core: leaf package for cross-domain legal-graph primitives.

This package MUST remain a leaf dependency. It must not import from
``domain_core``, ``rag_engine``, ``kg_builder``, ``llm_orchestrator``,
``eval``, ``apps.api``, ``apps.web``, or ``scripts``. Cross-checked by
``packages/legal_core/tests/test_import_boundary.py``.

Spec: docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md
"""

from legal_core.graph.factor_assertion import (
    ExtractionMethod,
    FactorAssertion,
    FactorPolarity,
)
from legal_core.graph.factor_value import FactorValue, FactorValueType
from legal_core.graph.graph_quality import GraphQualityScore

__all__ = [
    "ExtractionMethod",
    "FactorAssertion",
    "FactorPolarity",
    "FactorValue",
    "FactorValueType",
    "GraphQualityScore",
]
