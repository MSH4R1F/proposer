"""LLM-based KG enrichment builder (SHA-34).

Composes with GraphBuilder: the LLM extractor takes a base KG (built from
the CaseFile via GraphBuilder) plus the raw intake transcript / narrative,
and adds Event nodes and Evidence→Claim support edges that the structured
CaseFile schema can't capture cleanly.

Pipeline:
    1. GraphBuilder(case_file) → base KG  (existing path)
    2. LLMKGBuilder(llm_client).enrich(kg, transcript, case_file) → enriched KG
    3. KGValidator (SHA-35) → raises on hard logic contradictions

The LLM output is Pydantic-validated before any node/edge gets inserted;
malformed responses produce zero new nodes (graceful degradation), not
exceptions.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any, List, Optional

import structlog
from pydantic import BaseModel, Field, ValidationError, field_validator

from ..models.edges import Edge, EdgeType
from ..models.graph import KnowledgeGraph
from ..models.nodes import (
    ClaimedAmountNode,
    EventNode,
    EvidenceNode,
    IssueNode,
    NodeType,
)

logger = structlog.get_logger()


# Allowed event types — must match the prompt's enum exactly so the LLM
# can't sneak novel types past the validator.
_ALLOWED_EVENT_TYPES = {
    "tenancy_start",
    "tenancy_end",
    "inspection",
    "damage_discovered",
    "complaint_made",
    "repair_requested",
    "deposit_paid",
    "deposit_protected",
    "deposit_returned",
    "notice_served",
    "check_out",
    "mediation_started",
    "other",
}


class LLMEvent(BaseModel):
    """One event extracted from the transcript.

    Field is `event_date` (not `date`) to avoid shadowing the `datetime.date`
    class inside Pydantic's resolved-annotation namespace. JSON input still uses
    "date" via the alias.
    """

    event_type: str
    event_date: Optional[date] = Field(default=None, alias="date")
    description: str
    actors: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    model_config = {"populate_by_name": True}

    @field_validator("event_date", mode="before")
    @classmethod
    def _coerce_date(cls, value: Any) -> Any:
        """Allow ISO date strings, treat 'null'/empty as None."""
        if value is None or value == "":
            return None
        if isinstance(value, str):
            v = value.strip().lower()
            if v in {"null", "none", "unknown"}:
                return None
            try:
                return datetime.strptime(value.strip(), "%Y-%m-%d").date()
            except ValueError as exc:
                raise ValueError(f"Invalid ISO date: {value!r}") from exc
        return value


class LLMEvidenceClaimLink(BaseModel):
    """One Evidence-supports-Claim link extracted from the transcript."""

    evidence_description: str
    claim_description: str
    claimant: str  # 'tenant' or 'landlord'
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class LLMExtraction(BaseModel):
    """Pydantic schema for the LLM's KG-extraction output."""

    events: List[LLMEvent] = Field(default_factory=list)
    evidence_supports_claims: List[LLMEvidenceClaimLink] = Field(default_factory=list)
    no_new_info: bool = False


class LLMKGBuilder:
    """Enriches a base KG with LLM-extracted Events and Evidence→Claim edges."""

    def __init__(
        self,
        llm_client: Any,
        min_confidence: float = 0.5,
        validate: bool = True,
    ):
        """
        Args:
            llm_client: BaseLLMClient — the same client type used elsewhere.
            min_confidence: drop extracted items below this confidence threshold.
            validate: run KGValidator after enrichment (raises per SHA-35).
        """
        self.llm = llm_client
        self.min_confidence = min_confidence
        self.validate = validate

    async def enrich(
        self,
        kg: KnowledgeGraph,
        transcript: str,
        case_summary: str = "",
    ) -> KnowledgeGraph:
        """Add LLM-extracted Event nodes + Evidence→Claim edges to `kg`.

        Args:
            kg: base KG from GraphBuilder.
            transcript: raw intake transcript or assembled narrative.
            case_summary: short summary of the CaseFile already extracted —
                given to the LLM as context so it can match evidence/claim
                descriptions to existing nodes.

        Returns:
            Same KG instance, mutated in place. Returns kg even when no new
            nodes/edges added (e.g. transcript empty, LLM call fails).

        Raises:
            KGValidationError: when validate=True and the enriched graph
                violates hard temporal logic (delegated to KGValidator).
        """
        if not transcript or not transcript.strip():
            logger.debug("llm_kg_enrich_empty_transcript", case_id=kg.case_id)
            return kg

        # Local import — keeps kg_builder optionally decoupled from llm_orchestrator
        # at module load time (prompts only needed at enrich-call time).
        from llm_orchestrator.prompts.kg_extraction import (
            KG_EXTRACTION_SYSTEM_PROMPT,
            KG_EXTRACTION_USER_PROMPT,
        )

        user_prompt = KG_EXTRACTION_USER_PROMPT.format(
            case_summary=case_summary or "(no prior case summary)",
            transcript=transcript[:8000],  # cap input length
        )

        try:
            response = await self.llm.generate(
                messages=[{"role": "user", "content": user_prompt}],
                system_prompt=KG_EXTRACTION_SYSTEM_PROMPT,
                max_tokens=2000,
                temperature=0.1,  # deterministic-ish extraction
            )
        except Exception as exc:
            logger.error(
                "llm_kg_enrich_call_failed",
                case_id=kg.case_id,
                error=str(exc),
            )
            return kg

        extraction = self._parse_extraction_response(response, kg.case_id)
        if extraction is None or extraction.no_new_info:
            logger.debug("llm_kg_enrich_no_new_info", case_id=kg.case_id)
            return self._maybe_validate(kg)

        added_events = self._add_event_nodes(kg, extraction.events)
        added_edges = self._add_evidence_claim_edges(kg, extraction.evidence_supports_claims)

        logger.info(
            "llm_kg_enrich_complete",
            case_id=kg.case_id,
            added_events=added_events,
            added_edges=added_edges,
        )

        return self._maybe_validate(kg)

    def _maybe_validate(self, kg: KnowledgeGraph) -> KnowledgeGraph:
        if not self.validate:
            return kg
        from .validators import KGValidator  # local import to avoid circular

        return KGValidator(raise_on_error=True).validate(kg)

    def _parse_extraction_response(
        self, response: str, case_id: str
    ) -> Optional[LLMExtraction]:
        """Parse the LLM response into an LLMExtraction or return None."""
        cleaned = (response or "").strip()
        if "```json" in cleaned:
            start = cleaned.find("```json") + len("```json")
            end = cleaned.find("```", start)
            cleaned = cleaned[start : end if end != -1 else None].strip()
        elif cleaned.startswith("```"):
            start = cleaned.find("```") + 3
            end = cleaned.find("```", start)
            cleaned = cleaned[start : end if end != -1 else None].strip()

        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning(
                "llm_kg_extract_json_parse_failed",
                case_id=case_id,
                error=str(exc),
                preview=cleaned[:200],
            )
            return None

        try:
            return LLMExtraction.model_validate(payload)
        except ValidationError as exc:
            logger.warning(
                "llm_kg_extract_pydantic_validation_failed",
                case_id=case_id,
                error=str(exc),
            )
            return None

    def _add_event_nodes(
        self, kg: KnowledgeGraph, events: List[LLMEvent]
    ) -> int:
        """Insert validated Event nodes into the KG. Returns count added."""
        added = 0
        for ev in events:
            if ev.confidence < self.min_confidence:
                continue
            if ev.event_type not in _ALLOWED_EVENT_TYPES:
                logger.warning(
                    "llm_kg_event_unknown_type",
                    case_id=kg.case_id,
                    event_type=ev.event_type,
                )
                continue

            node_id = self._unique_event_id(kg, ev)
            node = EventNode(
                node_id=node_id,
                event_type=ev.event_type,
                event_date=ev.event_date,
                description=ev.description[:500],
                actors=[a for a in ev.actors if a in {"tenant", "landlord", "agent"}],
                confidence=ev.confidence,
                source="llm_extracted",
            )
            if kg.add_node(node):
                added += 1
        return added

    def _add_evidence_claim_edges(
        self, kg: KnowledgeGraph, links: List[LLMEvidenceClaimLink]
    ) -> int:
        """Insert Evidence-supports-Claim edges based on LLM-identified links."""
        evidence_nodes = [n for n in kg.nodes if n.node_type == NodeType.EVIDENCE]
        claim_nodes = [n for n in kg.nodes if n.node_type == NodeType.CLAIMED_AMOUNT]
        added = 0

        for link in links:
            if link.confidence < self.min_confidence:
                continue
            if link.claimant not in {"tenant", "landlord"}:
                continue

            ev_node = self._best_match(link.evidence_description, evidence_nodes)
            claim_node = self._best_match_claim(
                link.claim_description, link.claimant, claim_nodes
            )
            if ev_node is None or claim_node is None:
                continue

            edge = Edge.create(
                EdgeType.EVIDENCE_SUPPORTS,
                ev_node.node_id,
                claim_node.node_id,
                confidence=link.confidence,
                source="llm_extracted",
                description=f"LLM-identified support: {link.evidence_description[:80]}",
            )
            if kg.add_edge(edge):
                added += 1
        return added

    @staticmethod
    def _unique_event_id(kg: KnowledgeGraph, ev: LLMEvent) -> str:
        date_part = ev.event_date.isoformat() if ev.event_date else "undated"
        base = f"event_llm_{ev.event_type}_{date_part}"
        node_id = base
        suffix = 1
        while any(n.node_id == node_id for n in kg.nodes):
            node_id = f"{base}_{suffix}"
            suffix += 1
        return node_id

    @staticmethod
    def _best_match(query: str, candidates: List[Any]) -> Optional[Any]:
        """Tiny lexical match — enough for narrative-described evidence/claims.

        Picks the candidate whose description has the most token-overlap with
        the query. Returns None if no candidate has any overlap (avoids
        forcing spurious links).
        """
        if not candidates:
            return None
        query_tokens = set(re.findall(r"\w+", (query or "").lower()))
        if not query_tokens:
            return None
        best, best_score = None, 0
        for c in candidates:
            desc = getattr(c, "description", "") or ""
            tokens = set(re.findall(r"\w+", desc.lower()))
            tokens.add(getattr(c, "evidence_type", "") or "")
            score = len(query_tokens & tokens)
            if score > best_score:
                best, best_score = c, score
        return best if best_score > 0 else None

    @staticmethod
    def _best_match_claim(
        query: str, claimant: str, candidates: List[Any]
    ) -> Optional[Any]:
        """Match the LLM-described claim to one of the right party's claims."""
        same_party = [c for c in candidates if getattr(c, "claimant", "") == claimant]
        return LLMKGBuilder._best_match(query, same_party)
