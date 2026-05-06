"""Iterative retrieval agent — Architecture C.

State machine over the existing ``Tool``/``ToolSet`` primitives. The
agent curates retrieval context for one (case, issue) pair across up
to ``MAX_ITER=4`` iterations, then hands the curated context to the
downstream IRAC predictor.

Iteration 1 is Architecture B (one-shot QueryPlanner): the planner
emits 3-5 queries, we run them in parallel through the RAG envelope,
and seed ``state.chunks_so_far``.

Iterations 2-4 run a sufficiency judge: one LLM call per iteration
that picks ONE tool action via Anthropic's tool-use API. We force
``tool_choice={"type": "any"}`` for iters 2..MAX_ITER-2 (the model
must call a tool, never emit free text), and force
``tool_choice={"type": "tool", "name": "finalize"}`` at iter
MAX_ITER-1 to get a deterministic terminator.

Termination terminator values (in priority order):
    JUDGE_OK       finalize(confidence_score >= 0.70)
    JUDGE_ABSTAIN  abstain(reason)
    DUP_QUERY      retrieve raised duplicate (handled by tool dispatch)
    JUDGE_INVALID  2 consecutive unknown tool / invalid args
    TOKEN_CAP      cumulative tokens exceeded
    CHUNKS_CAP     cumulative chunks exceeded
    MAX_ITER       iteration cap reached without finalize/abstain

Spec: ``docs/research/agentic-retrieval-anthropic-sdk-cookbook-2026-05-05.md``
§2.2-2.6 plus ``agentic-retrieval-architecture-research-2026-05-05.md``
§3.1-3.3.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from ..agent_loop.context import ToolContext
from ..agent_loop.tool import ToolSet
from ..agent_loop.trace import TraceTerminationReason
from ..clients.claude_client import ClaudeClient
from ..models.agent_state import AgentAction, AgentChunk, AgentState, PlannedQuery
from ..prompts.agent_prompts import (
    SUFFICIENCY_JUDGE_SYSTEM,
    SUFFICIENCY_JUDGE_VERSION,
    render_state_for_judge,
)
from .query_planner import QueryPlanner
from .retrieval_agent_tools import (
    RetrievalToolContext,
    build_retrieval_toolset,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Loop constants — these are HARD CAPS, not advisory.
# Per architecture research §3.3 termination policy.
# ---------------------------------------------------------------------------

MAX_ITER = 4
"""Hard cap on iterations including iter 1 (the planner). Architecture
research §3.3: ReAct used 7 on HotpotQA; Ombudsman cases are simpler
because evidence axes are bounded (liability + remedy + maybe
vulnerability). 4 is enough; promote-or-deprecate gate in plan §11
fires if median iter_count saturates near 4 — that means cases need
more iterations than the cap allows."""

MAX_TOKENS_TOOL_TRACE = 8_000
"""Cumulative input+output tokens across the loop's LLM calls. Above
this, terminate with TOKEN_CAP. ``MAX_TOKENS`` from the spec."""

MAX_CHUNKS = 24
"""Cumulative deduped chunks. Above this, terminate with CHUNKS_CAP.
Reranker quality drops past ~24 on legal text per the retrieval
research."""

MAX_INVALID_TOOL_NAMES = 2
"""Consecutive iterations where the judge emitted an unknown tool
or invalid args. After 2, terminate with JUDGE_INVALID and let the
caller fall back to static_two_pass."""

JUDGE_CONFIDENCE_THRESHOLD = 0.70
"""Threshold for a finalize() call to be accepted as JUDGE_OK. Below
this, the loop treats finalize as a low-confidence signal and keeps
iterating subject to the iter cap. EviMem reports rho=0.93 between
LLM-emitted confidence and oracle sufficiency on long-context
memory; 0.70 is the published commit-tier threshold."""

PER_PURPOSE_K = 6
"""Top-K each iter-1 query retrieves before fusion. Iter 1 fans out
3-5 queries; with K=6 each that's at most 30 candidates pre-dedup
which trims comfortably under MAX_CHUNKS."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_agent_loop(
    *,
    llm_client: ClaudeClient,
    rag: Any,
    case_summary: str,
    issue_type: str,
    gold_case_id: str = "",
    kg: Any = None,
    kg_hint: str = "",
    query_planner: Optional[QueryPlanner] = None,
    toolset: Optional[ToolSet] = None,
    judge_model: Optional[str] = None,
) -> AgentState:
    """Run the iterative retrieval agent.

    Returns ``AgentState`` with ``terminator`` populated. Never raises
    on judge errors — falls back via ``terminator='judge_invalid'``
    so the caller can route to a deterministic baseline.

    Args:
        llm_client: ClaudeClient. Used for both the planner and the
            sufficiency judge in this branch.
        rag: An eval-time-filtered RAG pipeline (typically an
            ``_EvalFilteredRAGPipeline`` instance). Leakage filters
            inherit from this object — the agent does not construct a
            raw RAGPipeline.
        case_summary: Plain-English description of the case (already
            stripped of post-decision fields by the eval adapter).
        issue_type: Issue type string.
        gold_case_id: The case_id under analysis. Empty string in
            tests; required in real eval to enforce self-reference
            blocking.
        kg: Optional KnowledgeGraph for ``check_kg_fact`` lookups.
        kg_hint: Optional one-line summary handed to the planner.
        query_planner: Override the planner; default constructs one
            using ``llm_client``.
        toolset: Override the toolset; default uses
            ``build_retrieval_toolset()``.
        judge_model: Optional model override for the judge calls.
    """
    state = AgentState(case_id=gold_case_id, issue_type=issue_type)
    planner = query_planner or QueryPlanner(llm_client=llm_client)
    tools = toolset or build_retrieval_toolset()

    # ── Iteration 1: QueryPlanner (Architecture B) ──
    plan = await planner.plan(
        case_summary=case_summary,
        issue_type=issue_type,
        kg_hint=kg_hint,
        gold_case_id=gold_case_id,
    )
    state.iter = 1
    state.tokens_used += plan.decomposer_tokens_in + plan.decomposer_tokens_out

    if not plan.queries:
        # The planner produced nothing usable. Two options: fall back
        # to a static query, or terminate with JUDGE_INVALID. Choose
        # the latter — the caller (engine) routes to static_two_pass
        # for this case, which is honest about what happened.
        state.terminator = TraceTerminationReason.JUDGE_INVALID.value
        return state

    new_chunks = await _run_planned_queries_in_parallel(
        plan.queries, rag=rag, gold_case_id=gold_case_id, k=PER_PURPOSE_K
    )
    state.add_chunks(new_chunks)
    state.queries_so_far.extend([(q.purpose, q.text) for q in plan.queries])

    # If the planner's queries surfaced nothing at all, we have no
    # evidence to feed the judge. Terminate cleanly.
    if not state.chunks_so_far:
        state.terminator = TraceTerminationReason.JUDGE_ABSTAIN.value
        return state

    # ── Iterations 2..MAX_ITER: sufficiency judge ──
    ctx = RetrievalToolContext(
        rag=rag,
        kg=kg,
        agent_state=state,
        gold_case_id=gold_case_id,
    )
    tool_schemas = tools.anthropic_schemas()
    system_blocks = _build_judge_system_blocks()
    messages: List[Dict[str, Any]] = []

    while state.iter < MAX_ITER:
        state.iter += 1

        # Cap checks BEFORE issuing the LLM call.
        if state.tokens_used > MAX_TOKENS_TOOL_TRACE:
            state.terminator = TraceTerminationReason.TOKEN_CAP.value
            return state
        if len(state.chunks_so_far) > MAX_CHUNKS:
            state.terminator = TraceTerminationReason.CHUNKS_CAP.value
            return state

        # Tool-choice control: force finalize at iter == MAX_ITER (the
        # last allowed iteration). On every earlier iter, force "any"
        # tool with serial dispatch so we get exactly one tool_use
        # block per turn.
        if state.iter == MAX_ITER:
            tool_choice: Dict[str, Any] = {
                "type": "tool",
                "name": "finalize",
            }
        else:
            tool_choice = {
                "type": "any",
                "disable_parallel_tool_use": True,
            }

        # Fresh user message each turn — short, since the system
        # prefix does the heavy lifting (cached).
        user_text = render_state_for_judge(state)
        # Keep the message history short: one user turn, the
        # assistant response, the tool_result, repeat. Re-rendering
        # state every turn means we don't depend on the model
        # remembering it across long histories.
        messages = [{"role": "user", "content": user_text}]

        try:
            response = await llm_client.run_agent_turn(
                system_prompt=system_blocks,
                messages=messages,
                tool_schemas=tool_schemas,
                model=judge_model,
                max_tokens=512,
                tool_choice=tool_choice,
            )
        except Exception as exc:
            logger.warning(
                "judge_llm_error",
                extra={"err": str(exc), "iter": state.iter},
            )
            state.invalid_name_streak += 1
            if state.invalid_name_streak >= MAX_INVALID_TOOL_NAMES:
                state.terminator = TraceTerminationReason.JUDGE_INVALID.value
                return state
            continue

        state.tokens_used += response.tokens_in + response.tokens_out

        tool_use_blocks = [
            b
            for b in response.content_blocks
            if isinstance(b, dict) and b.get("type") == "tool_use"
        ]

        if len(tool_use_blocks) != 1:
            # 0 or >1 tool calls — disable_parallel_tool_use should
            # have prevented >1, but defend anyway.
            state.invalid_name_streak += 1
            logger.warning(
                "judge_unexpected_block_count",
                extra={
                    "iter": state.iter,
                    "count": len(tool_use_blocks),
                    "stop_reason": response.stop_reason,
                },
            )
            if state.invalid_name_streak >= MAX_INVALID_TOOL_NAMES:
                state.terminator = TraceTerminationReason.JUDGE_INVALID.value
                return state
            continue

        tool_use = tool_use_blocks[0]
        tool_name = str(tool_use.get("name", ""))
        tool_input = tool_use.get("input") or {}
        if not isinstance(tool_input, dict):
            tool_input = {}

        # Record judge action BEFORE dispatch so trace captures it
        # even if dispatch raises. confidence_score is only on
        # finalize — others get None.
        action = AgentAction(
            tool=_normalise_tool_name(tool_name),
            input=dict(tool_input),
            rationale="",
            confidence_score=_extract_confidence(tool_name, tool_input),
        )
        state.judge_log.append(action)

        # Dispatch through the existing ToolSet plumbing. Errors are
        # captured into ToolResult.is_error and will surface back to
        # the model on the next turn (the existing AgentLoop pattern;
        # see agent_loop/loop.py:280-345 for the full version).
        result = await tools.dispatch(tool_name, tool_input, ctx)

        if result.is_error:
            # An invalid tool name, leakage hit, dedup, or unknown
            # chunk_id. Streak count goes up; if we hit the cap, fall
            # back to JUDGE_INVALID.
            state.invalid_name_streak += 1
            if state.invalid_name_streak >= MAX_INVALID_TOOL_NAMES:
                state.terminator = TraceTerminationReason.JUDGE_INVALID.value
                return state
            # Otherwise just continue to next iter — the user
            # message renderer will surface the blocked_queries
            # list so the judge can self-correct.
            continue

        # Successful dispatch resets the streak.
        state.invalid_name_streak = 0

        # Terminator paths: finalize (with sufficient confidence)
        # and abstain. dup_query is captured via is_error above.
        if tool_name == "finalize":
            conf = _extract_confidence(tool_name, tool_input)
            if conf is not None and conf >= JUDGE_CONFIDENCE_THRESHOLD:
                state.terminator = TraceTerminationReason.JUDGE_OK.value
                return state
            # Low-confidence finalize: keep iterating subject to caps.
            # The judge should re-evaluate next turn now that
            # rendered state shows the previous attempt.
            logger.info(
                "judge_low_confidence_finalize",
                extra={"iter": state.iter, "confidence": conf},
            )
            continue

        if tool_name == "abstain":
            state.terminator = TraceTerminationReason.JUDGE_ABSTAIN.value
            return state

        # Otherwise the tool was retrieve/extract_amounts/check_kg_fact.
        # State has been mutated by the tool. Loop to the next iter.

    # We exit the while via state.iter < MAX_ITER. If we got here, we
    # passed iter MAX_ITER without an early terminator — the forced
    # finalize at iter MAX_ITER must have produced a low-conf result
    # (or hit an error path that didn't terminate). Mark MAX_ITER.
    state.terminator = TraceTerminationReason.MAX_ITER.value
    return state


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _build_judge_system_blocks() -> List[Dict[str, Any]]:
    """System prompt as a list of text blocks with one cache_control
    breakpoint on the static rules text. Keeps the per-turn tax to
    just the user message (which changes each iter)."""
    return [
        {
            "type": "text",
            "text": (
                f"# sufficiency_judge_version: {SUFFICIENCY_JUDGE_VERSION}\n\n"
                + SUFFICIENCY_JUDGE_SYSTEM
            ),
            "cache_control": {"type": "ephemeral"},
        }
    ]


async def _run_planned_queries_in_parallel(
    queries: List[PlannedQuery],
    *,
    rag: Any,
    gold_case_id: str,
    k: int,
) -> List[AgentChunk]:
    """Fan out the planner's queries in parallel and collect results.

    Each query goes through the same RAG envelope the rest of the
    pipeline uses, so leakage filters are inherited. Failures of one
    query do not abort the others — a partially-successful plan is
    still useful to the judge.
    """
    from .retrieval_agent_tools import (
        ToolDispatchError,
        _call_rag_retrieve,
        _to_agent_chunk,
        assert_query_safe,
    )

    async def _one(q: PlannedQuery) -> List[AgentChunk]:
        try:
            assert_query_safe(q.text, gold_case_id)
        except ToolDispatchError:
            logger.info(
                "planner_query_blocked_late",
                extra={"purpose": q.purpose, "query": q.text},
            )
            return []
        try:
            raw = await _call_rag_retrieve(
                rag=rag, query=q.text, k=k, section_type=None
            )
        except Exception as exc:
            logger.warning(
                "planner_query_rag_error",
                extra={"err": str(exc), "query": q.text},
            )
            return []
        return [_to_agent_chunk(r, purpose=q.purpose) for r in raw]

    results = await asyncio.gather(*(_one(q) for q in queries))
    flat: List[AgentChunk] = []
    for batch in results:
        flat.extend(batch)
    return flat


def _normalise_tool_name(name: str) -> str:
    """Map an arbitrary string back to one of our five tool literals.

    AgentAction.tool is typed as a Literal[...]; if the model emits
    a name outside the set the dispatch layer already caught it. We
    just need to avoid raising on the AgentAction construction so
    the trace records the raw call. Falls back to the string
    unchanged — Pydantic will reject if it's truly invalid, in which
    case the caller has already routed to is_error above.
    """
    valid = {"retrieve", "extract_amounts", "check_kg_fact", "finalize", "abstain"}
    return name if name in valid else "retrieve"  # safe default for trace shape


def _extract_confidence(
    tool_name: str, tool_input: Dict[str, Any]
) -> Optional[float]:
    """Pull confidence_score off a finalize() input. None for other tools."""
    if tool_name != "finalize":
        return None
    raw = tool_input.get("confidence_score")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None
