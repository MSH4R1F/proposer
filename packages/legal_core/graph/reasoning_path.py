"""ReasoningPath: a chain through the KG that justifies an outcome.

Per spec §5, a ``ReasoningPath`` records the ordered sequence of KG nodes
walked from supporting evidence up to a per-issue ``OutcomeComponent``.
The canonical chain shape is:

    EvidenceSpan -> FactorAssertion -> Proposition -> OutcomeComponent

but the model only enforces the structural minimum (``node_chain`` has at
least two node IDs — a single node is not a "path"). Higher-level
validators (e.g. PR 6's ``EvidencePathValidator``) are responsible for
checking that the chain shape matches an allowed pattern.

Frozen Pydantic v2 leaf model with ``extra="forbid"`` so the path is
safe to hash / cache and resistant to accidental mutation while
traversing the prediction graph in PR 4 / PR 5 / PR 6.

Spec: docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md §5
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field


class ReasoningPath(BaseModel):
    """Ordered chain of KG node IDs that justifies an OutcomeComponent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reasoning_path_id: str
    outcome_component_id: str
    node_chain: List[str] = Field(min_length=2)
    edges_used: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
