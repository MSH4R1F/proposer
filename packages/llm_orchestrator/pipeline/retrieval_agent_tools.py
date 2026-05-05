"""Tool definitions for the iterative retrieval agent (Architecture C).

Four tools, closed list. Adding a tool requires the §5.3 review gate
in ``docs/research/hybrid-rag-agentic-retrieval-plan-2026-05-05.md``.

    - retrieve(query, purpose, section_type=None, k=5)
    - extract_amounts(chunk_id)
    - check_kg_fact(field)
    - finalize(reason, confidence_score)

Tools register through the existing ``@tool`` decorator from
``packages/llm_orchestrator/agent_loop/tool.py`` so the standard
``ToolSet`` plumbing (schema generation, dispatch, error wrapping)
works for retrieval-agent runs the same way it does for the mediator
agent.

Leakage guards are enforced HERE, not in the prompt. The system
prompt instructs the model not to issue outcome-revealing queries
or self-reference the case, but the dispatcher is the bright line —
no query reaches ``rag.retrieve`` until ``assert_query_safe`` passes.
That makes the leakage audit (plan §5.4) defensible: a regex hit
either drops the query or raises a ``ToolDispatchError`` returned to
the model as ``is_error=True`` content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from ..agent_loop.context import ToolContext
from ..agent_loop.tool import Tool, ToolResult, ToolSet, tool
from ..models.agent_state import (
    AgentAmount,
    AgentChunk,
    AgentKGFact,
    AgentState,
    PurposeLiteral,
)
from .comparator_extractor import extract_pound_amounts


# ---------------------------------------------------------------------------
# Context extension
# ---------------------------------------------------------------------------


@dataclass
class RetrievalToolContext(ToolContext):
    """ToolContext extended with retrieval-agent-only state.

    The @tool decorator's first-parameter check insists on the parent
    ``ToolContext`` annotation (strict identity), so tool functions
    declare ``ctx: ToolContext`` and runtime-cast to this subclass via
    ``_as_retrieval_ctx`` below. That keeps schema-generation working
    while letting tools read and mutate per-loop state safely.
    """

    agent_state: Optional[AgentState] = None
    """Per-loop accumulated state (chunks, queries, amounts, kg facts).

    Required for tool dispatch; ``None`` only during construction.
    """

    gold_case_id: str = ""
    """The case_id under analysis. Used by ``assert_query_safe`` to
    block queries that self-reference the case."""

    # Reserved for the comparator_extractor: a ``chunk_id -> text``
    # lookup for chunks that have been retrieved but whose text isn't
    # carried on AgentChunk for size reasons. Today AgentChunk carries
    # text directly so this stays empty; kept for future ergonomics.
    chunk_text_overrides: Dict[str, str] = field(default_factory=dict)


def _as_retrieval_ctx(ctx: ToolContext) -> RetrievalToolContext:
    """Runtime cast with a clear error if the wrong context is used.

    Tools cannot be called with a plain ``ToolContext`` because every
    tool needs ``agent_state``. This raises a ``ToolDispatchError``
    rather than ``AttributeError`` so the loop can render a useful
    message to the model.
    """
    if not isinstance(ctx, RetrievalToolContext):
        raise ToolDispatchError(
            "Internal error: retrieval-agent tools require RetrievalToolContext."
        )
    if ctx.agent_state is None:
        raise ToolDispatchError(
            "Internal error: RetrievalToolContext missing agent_state."
        )
    return ctx


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ToolDispatchError(Exception):
    """Raised when a tool call is rejected by the dispatcher.

    Surfaced back to the model as a ``tool_result`` with
    ``is_error=True`` so the model can self-correct on the next turn.
    Two consecutive raises trigger ``terminator=judge_invalid``.
    """


# ---------------------------------------------------------------------------
# Leakage guards
# ---------------------------------------------------------------------------

# Outcome-revealing phrases the agent must never include in a query.
# Order is significant only for readability; ``re.IGNORECASE`` covers
# casing variants. See ``docs/research/hybrid-rag-agentic-retrieval-plan-2026-05-05.md``
# §5.1 for the rationale.
FORBIDDEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"tenant\s*win", re.IGNORECASE),
    re.compile(r"landlord\s*win", re.IGNORECASE),
    re.compile(r"compensation\s*£", re.IGNORECASE),
    re.compile(r"awarded\s*£", re.IGNORECASE),
    re.compile(r"maladministration\s*found", re.IGNORECASE),
    re.compile(r"severe\s*maladministration\s*found", re.IGNORECASE),
    re.compile(r"\bservice\s*failure\s*upheld\b", re.IGNORECASE),
)


def assert_query_safe(query: str, gold_case_id: str) -> None:
    """Reject queries that would constitute leakage.

    Two checks:
        1. The query must not contain the gold case_id (self-reference).
        2. The query must not contain any outcome-revealing phrase from
           ``FORBIDDEN_PATTERNS``.

    Failure raises ``ToolDispatchError`` with a corrective message
    naming the rule violated. The agent loop logs the rejection in
    ``state.blocked_queries`` for trace audit and surfaces it back to
    the model so it can rephrase.

    Empty string ``gold_case_id`` skips the self-reference check —
    used in tests where there is no analysed case.
    """
    if gold_case_id and gold_case_id.lower() in query.lower():
        raise ToolDispatchError(
            f"Query references the case under analysis ({gold_case_id!r}). "
            "Issue a query about evidence types or general patterns, not "
            "about a specific case ID."
        )
    for pat in FORBIDDEN_PATTERNS:
        if pat.search(query):
            raise ToolDispatchError(
                f"Query contains an outcome-revealing phrase matching "
                f"/{pat.pattern}/. Rephrase as a neutral evidence query."
            )


# ---------------------------------------------------------------------------
# Tool argument models
# ---------------------------------------------------------------------------


class RetrieveArgs(BaseModel):
    """Args for the ``retrieve`` tool.

    Bounds are enforced by Pydantic so the dispatcher never sees
    nonsense values. ``query`` length bounds drive the model toward
    short, retrieval-friendly noun phrases (DMQR-RAG warns about noisy
    over-expansion when queries get long).
    """

    query: str = Field(
        ...,
        min_length=4,
        max_length=200,
        description=(
            "4-15 word noun phrase or fragment describing the evidence "
            "you want to retrieve. Plain English; do not include the "
            "case_id under analysis or any outcome-revealing phrase."
        ),
    )
    purpose: PurposeLiteral = Field(
        ...,
        description=(
            "Why you need this evidence. Used to weight RRF fusion. One "
            "of: liability, remedy, vulnerability, timeline, adhoc."
        ),
    )
    section_type: Optional[
        Literal["facts", "reasoning", "orders", "determination"]
    ] = Field(
        default=None,
        description=(
            "Optional filter to restrict results to one section type "
            "of Ombudsman determinations. Use ``orders`` or "
            "``determination`` to surface compensation amounts."
        ),
    )
    k: int = Field(
        default=5,
        ge=1,
        le=8,
        description="Number of chunks to return; default 5, max 8.",
    )


class ExtractAmountsArgs(BaseModel):
    chunk_id: str = Field(
        ...,
        min_length=1,
        description=(
            "Chunk identifier returned by an earlier retrieve call in "
            "THIS loop. Unknown chunk_ids are rejected."
        ),
    )


class CheckKGFactArgs(BaseModel):
    field: Literal[
        "vulnerability_flag",
        "awaabs_law_applies",
        "report_to_first_attendance_days",
        "complaint_stages_reached",
        "prior_offer_gbp",
        "outstanding_works_at_complaint_close",
    ] = Field(
        ...,
        description=(
            "One of the closed list of typed KG fields. Reading this "
            "field does NOT expose any gold-set outcome — those fields "
            "are stripped before the agent runs."
        ),
    )


class FinalizeArgs(BaseModel):
    reason: str = Field(
        default="",
        max_length=400,
        description=(
            "Short justification for stopping. Logged in the agent "
            "trace; not used by the predictor."
        ),
    )
    confidence_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Required: your confidence (0.0-1.0) that the gathered "
            "evidence is sufficient to predict the outcome. "
            "Below 0.70, the loop treats finalize as a low-confidence "
            "abstention and may keep iterating subject to caps."
        ),
    )


class AbstainArgs(BaseModel):
    reason: str = Field(
        ...,
        min_length=4,
        max_length=400,
        description=(
            "Why no liability-supporting evidence span exists. "
            "Recorded as 'uncertain' in the prediction. Do not abstain "
            "merely because evidence is mixed."
        ),
    )


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


@tool(
    description=(
        "Search the Housing Ombudsman case corpus for chunks relevant to "
        "your query. Eval-time leakage filters (excluded source IDs, "
        "max decision date) are applied automatically and CANNOT be "
        "disabled by you. Use this when you need additional evidence on "
        "a specific aspect of the case (liability facts, remedy "
        "comparators, vulnerability indicators, or timeline rules). DO "
        "NOT issue queries that name the case under analysis or contain "
        "outcome phrases like 'compensation £' or 'maladministration "
        "found' — the leakage guard will drop them and the iteration is "
        "wasted."
    ),
    max_output_chars=4_000,
)
async def retrieve(ctx: ToolContext, args: RetrieveArgs) -> dict[str, Any]:
    rctx = _as_retrieval_ctx(ctx)
    state = rctx.agent_state
    assert state is not None  # narrowed by _as_retrieval_ctx

    # Cycle / dedup guard.
    if state.has_query(args.purpose, args.query):
        raise ToolDispatchError(
            f"Duplicate query (purpose={args.purpose}, text={args.query!r}). "
            "Issue a different query, or call finalize()."
        )

    # Leakage guard. May raise ToolDispatchError; the agent_loop catches
    # the exception and returns is_error to the model.
    try:
        assert_query_safe(args.query, rctx.gold_case_id)
    except ToolDispatchError:
        # Record the blocked query in the trace audit list before
        # re-raising. The trace audit gate (plan §5.4) reads this list.
        state.blocked_queries.append(
            {
                "purpose": args.purpose,
                "query": args.query,
                "iter": state.iter,
            }
        )
        raise

    if rctx.rag is None:
        raise ToolDispatchError(
            "Retrieval is not available in this run."
        )

    # Run the RAG retrieve. Mode/leakage filters are inherited from the
    # _EvalFilteredRAGPipeline wrapper that the engine constructed —
    # we never construct a raw RAGPipeline here.
    rag_results = await _call_rag_retrieve(
        rag=rctx.rag,
        query=args.query,
        k=args.k,
        section_type=args.section_type,
    )

    # Normalise into AgentChunk records with the purpose tag preserved.
    new_chunks = [
        _to_agent_chunk(r, purpose=args.purpose) for r in rag_results
    ]
    added = state.add_chunks(new_chunks)
    state.queries_so_far.append((args.purpose, args.query))

    # Return a primitive dict — Tool.dispatch wraps it in ToolResult.
    return {
        "added_chunks": added,
        "total_chunks_so_far": len(state.chunks_so_far),
        "chunks": [
            {
                "chunk_id": c.chunk_id,
                "section_type": c.section_type,
                "score": c.score,
                # Keep model-visible text short to limit context cost
                # per iteration; full text stays on AgentChunk for
                # later prompt rendering.
                "text": c.text[:400],
            }
            for c in new_chunks
        ],
    }


@tool(
    description=(
        "Extract pound-sterling amounts from a chunk you have already "
        "retrieved. Returns each amount with its surrounding sentence. "
        "Use only after a retrieve call has surfaced an order or "
        "determination chunk. Unknown chunk_ids are rejected."
    ),
    max_output_chars=2_000,
)
async def extract_amounts(
    ctx: ToolContext, args: ExtractAmountsArgs
) -> dict[str, Any]:
    rctx = _as_retrieval_ctx(ctx)
    state = rctx.agent_state
    assert state is not None

    chunk = next(
        (c for c in state.chunks_so_far if c.chunk_id == args.chunk_id),
        None,
    )
    if chunk is None:
        raise ToolDispatchError(
            f"chunk_id {args.chunk_id!r} was not seen in any prior "
            "retrieve result this loop. Retrieve first, then extract."
        )

    text = rctx.chunk_text_overrides.get(args.chunk_id, chunk.text)
    raw_amounts = extract_pound_amounts(
        chunk_id=chunk.chunk_id,
        text=text,
        paragraph_id=chunk.paragraph_id,
    )
    amounts = [
        AgentAmount(
            chunk_id=a.chunk_id,
            paragraph_id=a.paragraph_id,
            amount_gbp=a.amount_gbp,
            surrounding_sentence=a.surrounding_sentence,
            raw_match=a.raw_match,
        )
        for a in raw_amounts
    ]
    state.amounts_extracted.extend(amounts)

    return {
        "chunk_id": chunk.chunk_id,
        "section_type": chunk.section_type,
        "extracted_count": len(amounts),
        "amounts": [a.model_dump() for a in amounts],
    }


@tool(
    description=(
        "Read one typed fact about the case under analysis from its "
        "knowledge graph. The field must be one of the closed enum. "
        "This tool does NOT expose ground-truth outcome, awarded "
        "amount, or any gold-set field — those are stripped before the "
        "agent runs."
    ),
    max_output_chars=500,
)
async def check_kg_fact(
    ctx: ToolContext, args: CheckKGFactArgs
) -> dict[str, Any]:
    rctx = _as_retrieval_ctx(ctx)
    state = rctx.agent_state
    assert state is not None

    fact_value, is_known = _read_kg_fact(rctx.kg, args.field)
    fact = AgentKGFact(
        field=args.field, value=fact_value, is_known=is_known
    )
    state.kg_facts_seen.append(fact)
    return fact.model_dump()


@tool(
    description=(
        "Stop retrieval and proceed to the IRAC prediction call. Call "
        "this when you have at least one liability-relevant chunk AND "
        "(at least one remedy-relevant chunk OR an extracted comparator "
        "amount). The reason is logged for audit; the confidence_score "
        "is required and used by the loop's termination gate "
        "(threshold 0.70 — below that, the loop may keep going)."
    ),
    max_output_chars=400,
)
async def finalize(ctx: ToolContext, args: FinalizeArgs) -> dict[str, Any]:
    # The loop intercepts ``finalize`` to set state.terminator; the
    # tool body just echoes the reason for trace logging. We do NOT
    # validate confidence_score >= threshold here because the loop has
    # the threshold (it may differ per matter type).
    return {
        "reason": args.reason,
        "confidence_score": args.confidence_score,
    }


@tool(
    description=(
        "Declare that no liability-supporting span exists in the "
        "retrieved evidence. Recorded as 'uncertain' in the prediction. "
        "Do NOT abstain because evidence is mixed — only when no chunk "
        "supports a liability finding at all."
    ),
    max_output_chars=400,
)
async def abstain(ctx: ToolContext, args: AbstainArgs) -> dict[str, Any]:
    return {"reason": args.reason}


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def build_retrieval_toolset() -> ToolSet:
    """Return the closed five-tool ToolSet for the retrieval agent.

    Five tools (one more than originally specified):
        retrieve, extract_amounts, check_kg_fact, finalize, abstain

    ``abstain`` was split out from ``finalize`` so the loop can
    distinguish ``judge_ok`` from ``judge_abstain`` terminators
    cleanly (per architecture research §3.3 termination policy).
    """
    return ToolSet(
        name="retrieval_agent_tools_v1",
        tools=(
            retrieve,
            extract_amounts,
            check_kg_fact,
            finalize,
            abstain,
        ),
    )


# ---------------------------------------------------------------------------
# Helpers — RAG and KG adapters
# ---------------------------------------------------------------------------


async def _call_rag_retrieve(
    *,
    rag: Any,
    query: str,
    k: int,
    section_type: Optional[str],
) -> List[Any]:
    """Invoke the RAG pipeline's retrieve method.

    The RAG envelope is provided by the engine — typically a
    ``_EvalFilteredRAGPipeline`` wrapper that injects leakage filters.
    We never construct a raw ``RAGPipeline`` here; we just call into
    whatever was provided.

    The expected interface is ``await rag.retrieve(query, k=...,
    section_type=...)`` returning a list of chunk-shaped objects. Real
    implementations may use ``filters`` envelopes; the agent does not
    construct them — it inherits whatever filters the engine set.
    """
    # Try the modern shape first; fall back to a legacy positional
    # signature if needed. The double-call protection here is small
    # cost compared to the readability gain.
    try:
        return await rag.retrieve(
            query=query,
            k=k,
            section_type=section_type,
        )
    except TypeError:
        # Legacy signature without ``section_type`` keyword. Drop the
        # filter; the reranker will still see the chunks and the
        # leakage envelope is unchanged.
        return await rag.retrieve(query=query, k=k)


def _to_agent_chunk(raw: Any, *, purpose: PurposeLiteral) -> AgentChunk:
    """Coerce a RAG result into an ``AgentChunk``.

    Accepts either a dict (test fakes) or an object with attributes
    (real ``DocumentChunk``). Missing fields fall back to safe
    defaults so the loop never crashes on a malformed result.
    """
    def get(key: str, default: Any = None) -> Any:
        if isinstance(raw, dict):
            return raw.get(key, default)
        return getattr(raw, key, default)

    source_id = str(get("source_id") or get("case_reference") or "unknown")
    paragraph_id_raw = get("paragraph_id") or get("paragraph")
    paragraph_id = str(paragraph_id_raw) if paragraph_id_raw is not None else None
    chunk_id = str(get("chunk_id") or f"{source_id}#{paragraph_id or 'p?'}")
    text = str(get("chunk_text") or get("text") or "")
    section_type = get("section_type")
    score = float(get("combined_score") or get("score") or 0.0)
    return AgentChunk(
        chunk_id=chunk_id,
        source_id=source_id,
        paragraph_id=paragraph_id,
        section_type=section_type,
        text=text,
        score=score,
        purpose=purpose,
    )


def _read_kg_fact(kg: Any, field: str) -> tuple[Any, bool]:
    """Read a typed fact from the knowledge graph, if present.

    The full implementation depends on the repairs ontology adapter
    (planned as F-KG-1 in the master plan). This shim returns
    ``(None, False)`` when the KG isn't available so the agent can
    still run end-to-end on cases where typed repairs facts haven't
    been wired yet — the audit just records ``is_known=False``.
    """
    if kg is None:
        return (None, False)
    # Prefer a domain-specific reader if the KG provides one; fall
    # back to attribute access. The mediator code uses a similar
    # pattern.
    reader = getattr(kg, "read_typed_fact", None)
    if callable(reader):
        try:
            result = reader(field)
        except Exception:
            return (None, False)
        if isinstance(result, tuple) and len(result) == 2:
            return result
        return (result, result is not None)
    return (None, False)
