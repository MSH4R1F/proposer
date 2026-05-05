"""Pydantic models for the iterative retrieval agent.

State and action types used by the retrieval agent loop. Kept separate
from ``prediction_v2.py`` because they are agent-internal concerns
(state machine bookkeeping) rather than prediction-pipeline outputs.

Companion:
- ``packages/llm_orchestrator/pipeline/agentic_retriever.py`` — the loop.
- ``packages/llm_orchestrator/pipeline/retrieval_agent_tools.py`` — the
  four tool implementations.
- ``docs/research/hybrid-rag-agentic-retrieval-plan-2026-05-05.md`` §3-§5
  for the leakage invariants and trace schema this model serialises to.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field


PurposeLiteral = Literal["liability", "remedy", "vulnerability", "timeline", "adhoc"]


class AgentChunk(BaseModel):
    """One retrieved chunk in the agent's accumulated state.

    Mirrors the fields the agent loop actually relies on; full RAG
    metadata is preserved on the underlying retriever object and can
    be re-resolved by chunk_id.
    """

    chunk_id: str
    """Stable identifier — typically ``<source_id>#<paragraph_id>``."""

    source_id: str
    """The source document ID. Used for dedup with paragraph_id."""

    paragraph_id: Optional[str] = None
    """Paragraph anchor when available."""

    section_type: Optional[str] = None
    """One of ``facts``, ``reasoning``, ``orders``, ``determination`` when known."""

    text: str
    """The chunk text. Truncated for prompt rendering by callers."""

    score: float = 0.0
    """Combined retrieval score the chunk arrived with."""

    purpose: Optional[PurposeLiteral] = None
    """Which purpose-tagged query surfaced this chunk."""


class AgentAmount(BaseModel):
    """One extracted GBP amount with provenance back to its chunk."""

    chunk_id: str
    paragraph_id: Optional[str] = None
    amount_gbp: float
    surrounding_sentence: str
    raw_match: str


class AgentKGFact(BaseModel):
    """One KG fact the agent has read about the case under analysis.

    Field is restricted to the closed enum in the ``check_kg_fact``
    tool schema (see ``retrieval_agent_tools.py``).
    """

    field: str
    value: Any = None
    is_known: bool = False


class AgentAction(BaseModel):
    """A single tool call selected by the sufficiency judge.

    Mirrors L-MARS's ``JudgeDecision`` schema with the addition of
    ``confidence_score`` (per EviMem ρ=0.93 between LLM-emitted
    confidence and oracle sufficiency on long-context tasks).
    """

    tool: Literal[
        "retrieve",
        "extract_amounts",
        "check_kg_fact",
        "finalize",
        "abstain",
    ]
    input: Dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    confidence_score: Optional[float] = None
    """Required when tool == ``finalize``; ignored otherwise.

    Validated to ``[0, 1]`` by the loop, not by Pydantic, so the model
    can hand us an out-of-range value and we record the violation in
    the trace rather than raising mid-loop.
    """


class PlannedQuery(BaseModel):
    """One query in the iter-1 query plan.

    Output of the ``QueryPlanner`` (Architecture B). The agent's
    iter-1 chunks come from running every ``PlannedQuery`` in parallel
    and fusing with purpose-weighted RRF.
    """

    purpose: PurposeLiteral
    text: str
    rationale: str = ""


class QueryPlan(BaseModel):
    """Output of the ``QueryPlanner.plan(case, issue)`` LLM call."""

    queries: List[PlannedQuery] = Field(default_factory=list)
    decomposer_model: Optional[str] = None
    decomposer_tokens_in: int = 0
    decomposer_tokens_out: int = 0


class AgentState(BaseModel):
    """Mutable state the retrieval agent accumulates across iterations.

    Lives for the duration of one ``run_agent_loop`` call. Serialised
    into the agent trace at termination (see plan §3.6).
    """

    case_id: str
    issue_type: str

    iter: int = 0
    """Current iteration number. ``0`` before the first turn; ``1`` after
    the query planner runs (= "iter 1 = Architecture B" in the plan).
    """

    queries_so_far: List[Tuple[PurposeLiteral, str]] = Field(default_factory=list)
    """List of ``(purpose, query)`` pairs we have already issued. Used
    for cycle/dedup detection (see plan §5)."""

    chunks_so_far: List[AgentChunk] = Field(default_factory=list)
    """All retrieved chunks, deduped on insert by ``(source_id, paragraph_id)``."""

    kg_facts_seen: List[AgentKGFact] = Field(default_factory=list)
    amounts_extracted: List[AgentAmount] = Field(default_factory=list)

    tokens_used: int = 0
    """Cumulative tokens billed across the agent's LLM calls in this loop.

    NOT the same as the predictor's downstream call; that's the
    output assembler's concern.
    """

    invalid_name_streak: int = 0
    """Consecutive iterations where the model called an unknown tool or
    emitted invalid JSON. Reset to 0 on any successful dispatch.
    """

    judge_log: List[AgentAction] = Field(default_factory=list)
    """One entry per iteration ≥2 (the planner runs at iter 1 without
    going through the judge)."""

    blocked_queries: List[Dict[str, Any]] = Field(default_factory=list)
    """Queries dropped by the leakage guard. Preserved for the trace's
    ``leakage_audit.blocked_queries`` field — never replayed."""

    terminator: Optional[str] = None
    """One of the values from ``TraceTerminationReason`` plus the
    retrieval-agent specific values added in trace.py. Set by the loop
    on termination; ``None`` while running."""

    def seen_chunk_keys(self) -> set[Tuple[str, Optional[str]]]:
        return {(c.source_id, c.paragraph_id) for c in self.chunks_so_far}

    def add_chunks(self, new_chunks: List[AgentChunk]) -> int:
        """Dedupe + append. Returns the count actually added."""
        seen = self.seen_chunk_keys()
        added = 0
        for c in new_chunks:
            key = (c.source_id, c.paragraph_id)
            if key in seen:
                continue
            self.chunks_so_far.append(c)
            seen.add(key)
            added += 1
        return added

    def has_query(
        self, purpose: PurposeLiteral, query: str
    ) -> bool:
        """Return True if (purpose, query) was already issued this loop."""
        return (purpose, query) in self.queries_so_far
