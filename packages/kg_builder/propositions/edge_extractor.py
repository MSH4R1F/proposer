"""Typed edge extractor for proposition graphs (SHA-36 Task 7).

Pure component: takes accepted propositions from one document plus an LLM
client (duck-typed to ``ClaudeClient.generate_structured``) and emits
validated :class:`~kg_builder.propositions.models.PropositionEdge`
objects with deterministic ids.

Critical design constraint: the edge extractor does NOT see the full
decision text. It receives only the accepted propositions' ids, types,
and text. The decision text was already filtered through Task 6's
pipeline; minimising the surface area limits prompt-injection risk and
keeps token cost down.

Persistence happens elsewhere (Task 9 CLI). The extractor's contract is:

  * < 2 propositions in → empty result, zero LLM calls.
  * One LLM call per document via ``generate_structured``.
  * Each returned edge item is validated:
      - endpoints must be in the input proposition_id set
      - no self-loops
      - ``edge_type`` must be a valid :class:`PropositionEdgeType`
      - ``confidence`` >= ``min_confidence``
      - rationale <= 500 chars (if present)
      - duplicates by (from, to, edge_type) triple are dropped
  * Deterministic edge ids are assigned **locally** via
    :func:`deterministic_edge_id` — anything the LLM might emit as an
    id is ignored.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional, Sequence
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from kg_builder.propositions.models import (
    Proposition,
    PropositionEdge,
    PropositionEdgeType,
    deterministic_edge_id,
)


# ---------------------------------------------------------------------------
# LLM response schema (Pydantic v2)
# ---------------------------------------------------------------------------


class ExtractedEdgeItem(BaseModel):
    """One edge as the LLM returns it.

    Endpoints reference ``proposition_id`` values from the input set
    (not arbitrary strings or ad-hoc identifiers). ``extra="ignore"`` so
    the LLM can return additional keys without breaking parsing.
    """

    model_config = ConfigDict(extra="ignore")

    from_proposition_id: UUID
    to_proposition_id: UUID
    edge_type: str  # validated against PropositionEdgeType in the converter
    rationale: Optional[str] = None
    confidence: float


class EdgeExtractionResponse(BaseModel):
    """Top-level LLM response schema."""

    model_config = ConfigDict(extra="ignore")

    edges: List[ExtractedEdgeItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Rejection accounting
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EdgeRejection:
    """One rejected LLM-emitted edge item, with a reason code for telemetry."""

    reason: str   # one of: "unknown_endpoint", "self_loop", "invalid_edge_type",
                  # "low_confidence", "duplicate_triple", "rationale_too_long",
                  # "validation_failed"
    snippet: str  # short hint for log/debug


@dataclass(frozen=True)
class EdgeExtractionResult:
    """Output of :meth:`LLMPropositionEdgeExtractor.extract_edges`."""

    edges: List[PropositionEdge]
    rejections: List[EdgeRejection]


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------


class LLMPropositionEdgeExtractor:
    """Extracts typed edges between propositions in the same document.

    See module docstring for the contract. The LLM client is duck-typed —
    we only need ``generate_structured(messages, system_prompt,
    response_model, max_tokens) -> response_model``.

    The LLM only sees: ``proposition_id`` (as string), ``proposition_type``,
    and ``text``. It does NOT see ``source_passage``, the full decision
    text, ``paragraph_ref``, or ``entities``. This is enforced by the
    user-prompt construction below and verified by the unit tests.
    """

    def __init__(
        self,
        llm_client,
        *,
        min_confidence: float = 0.5,
        max_tokens: int = 16384,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be in [0, 1]")
        self.llm = llm_client
        self.min_confidence = min_confidence
        self.max_tokens = max_tokens
        self.log = logger or logging.getLogger(__name__)

    async def extract_edges(
        self,
        document_id: UUID,
        propositions: Sequence[Proposition],
    ) -> EdgeExtractionResult:
        """Run edge extraction over a set of propositions from one document.

        Empty / singleton input returns an empty result with zero LLM calls.
        """
        if len(propositions) < 2:
            return EdgeExtractionResult(edges=[], rejections=[])

        accepted_ids = {p.proposition_id for p in propositions}

        # Build the LLM input payload. Only id / type / text are exposed —
        # NEVER source_passage, paragraph_ref, or entities.
        from kg_builder.propositions.prompts import (
            EDGE_EXTRACTION_SYSTEM_PROMPT,
            EDGE_EXTRACTION_USER_PROMPT,
        )

        proposition_lines = "\n".join(
            f"- id={p.proposition_id} type={p.proposition_type.value} text={p.text}"
            for p in propositions
        )
        user_prompt = EDGE_EXTRACTION_USER_PROMPT.format(
            document_id=document_id,
            propositions=proposition_lines,
        )
        response: EdgeExtractionResponse = await self.llm.generate_structured(
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=EDGE_EXTRACTION_SYSTEM_PROMPT,
            response_model=EdgeExtractionResponse,
            max_tokens=self.max_tokens,
        )

        accepted: List[PropositionEdge] = []
        rejections: List[EdgeRejection] = []
        seen_triples: set[tuple[UUID, UUID, str]] = set()

        for item in response.edges:
            # 1. endpoints must be in input set
            if (
                item.from_proposition_id not in accepted_ids
                or item.to_proposition_id not in accepted_ids
            ):
                rejections.append(EdgeRejection(
                    reason="unknown_endpoint",
                    snippet=f"{item.from_proposition_id} -> {item.to_proposition_id}",
                ))
                continue

            # 2. self-loop
            if item.from_proposition_id == item.to_proposition_id:
                rejections.append(EdgeRejection(
                    reason="self_loop",
                    snippet=str(item.from_proposition_id),
                ))
                continue

            # 3. enum validation
            try:
                edge_type = PropositionEdgeType(item.edge_type)
            except ValueError:
                rejections.append(EdgeRejection(
                    reason="invalid_edge_type",
                    snippet=item.edge_type[:80],
                ))
                continue

            # 4. confidence threshold
            if item.confidence < self.min_confidence:
                rejections.append(EdgeRejection(
                    reason="low_confidence",
                    snippet=f"{item.from_proposition_id} -> {item.to_proposition_id}",
                ))
                continue

            # 5. dedup by triple (first one wins)
            triple = (
                item.from_proposition_id,
                item.to_proposition_id,
                edge_type.value,
            )
            if triple in seen_triples:
                rejections.append(EdgeRejection(
                    reason="duplicate_triple",
                    snippet=(
                        f"{item.from_proposition_id} -> "
                        f"{item.to_proposition_id} ({edge_type.value})"
                    ),
                ))
                continue

            # 6. rationale length
            if item.rationale is not None and len(item.rationale) > 500:
                rejections.append(EdgeRejection(
                    reason="rationale_too_long",
                    snippet=item.rationale[:80],
                ))
                continue

            # 7. assemble domain edge with deterministic id. Add to
            # seen_triples only after the domain model accepts the edge —
            # otherwise a Pydantic-rejected item could shadow a valid
            # duplicate later in the list.
            try:
                edge = PropositionEdge(
                    edge_id=deterministic_edge_id(
                        item.from_proposition_id,
                        item.to_proposition_id,
                        edge_type,
                    ),
                    from_proposition_id=item.from_proposition_id,
                    to_proposition_id=item.to_proposition_id,
                    document_id=document_id,
                    edge_type=edge_type,
                    rationale=item.rationale,
                    confidence=item.confidence,
                )
            except Exception:
                rejections.append(EdgeRejection(
                    reason="validation_failed",
                    snippet=(
                        f"{item.from_proposition_id} -> {item.to_proposition_id}"
                    ),
                ))
                continue

            seen_triples.add(triple)
            accepted.append(edge)

        return EdgeExtractionResult(edges=accepted, rejections=rejections)


__all__ = [
    "ExtractedEdgeItem",
    "EdgeExtractionResponse",
    "EdgeRejection",
    "EdgeExtractionResult",
    "LLMPropositionEdgeExtractor",
]
