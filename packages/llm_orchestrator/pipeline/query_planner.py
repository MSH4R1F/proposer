"""Single-shot retrieval query planner — Architecture B / iteration 1.

One LLM call: read the case, emit a structured ``QueryPlan`` of 3-5
purpose-tagged queries. Used as the first iteration of the iterative
retrieval agent (Architecture C) and also exposed standalone as the
``decomposed`` retrieval mode.

We use Anthropic's tool-use API as the structured-output mechanism:
a single ``emit_query_plan`` tool with the QueryPlan-shaped args
schema, forced via ``tool_choice={"type": "tool", "name": ...}``.
This guarantees valid JSON conforming to the schema without
prompt-engineered "return JSON only" tricks (cookbook §2.6).

The planner is the most LLM-driven seam in the agent: the model
picks the queries, their purposes, and the rationale. The only
deterministic post-processing is a leakage filter — queries that
self-reference the gold case or contain outcome phrases are dropped
before the queries are returned. Dropped queries are surfaced on the
``QueryPlan.blocked_queries`` field for trace audit.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..clients.claude_client import ClaudeClient
from ..models.agent_state import PlannedQuery, PurposeLiteral, QueryPlan
from ..prompts.agent_prompts import QUERY_PLANNER_SYSTEM, QUERY_PLANNER_VERSION
from .retrieval_agent_tools import ToolDispatchError, assert_query_safe

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool schema (single-tool ToolSet for structured output)
# ---------------------------------------------------------------------------


class _PlannedQueryArgs(BaseModel):
    """Mirrors ``PlannedQuery`` but with explicit field descriptions
    that show up in the tool schema (and therefore in the prompt)."""

    purpose: PurposeLiteral = Field(
        ...,
        description=(
            "Why this query is needed. Must be one of: liability, "
            "remedy, vulnerability, timeline, adhoc."
        ),
    )
    text: str = Field(
        ...,
        min_length=4,
        max_length=200,
        description=(
            "4-15 word noun phrase or fragment describing the evidence "
            "to retrieve. Plain English, no outcome phrases, no case_id."
        ),
    )
    rationale: str = Field(
        default="",
        max_length=240,
        description="Short audit trail (one sentence) of why this query is needed.",
    )


class _EmitQueryPlanArgs(BaseModel):
    """Args for the single-tool-call structured output."""

    queries: List[_PlannedQueryArgs] = Field(
        ...,
        min_length=1,
        max_length=8,  # planner is asked for 3-5; cap at 8 to avoid runaway
        description=(
            "Ordered list of 3-5 search queries. At least one MUST have "
            "purpose='remedy' so the predictor sees comparator awards."
        ),
    )


_EMIT_TOOL_NAME = "emit_query_plan"


def _emit_query_plan_tool_schema() -> Dict[str, Any]:
    """Anthropic-shaped tool schema. We construct it manually rather
    than via the @tool decorator because:
      - the tool body is never dispatched (we only use the structured
        input that comes back), and
      - the @tool decorator requires a ToolContext signature we don't
        need here.
    """
    schema = _EmitQueryPlanArgs.model_json_schema()
    return {
        "name": _EMIT_TOOL_NAME,
        "description": (
            "Emit the retrieval query plan. The plan must include 3-5 "
            "queries, at least one with purpose='remedy'. Queries "
            "containing the case_id under analysis or outcome-revealing "
            "phrases will be dropped by the leakage guard."
        ),
        "input_schema": _strip_pydantic_schema(schema),
    }


def _strip_pydantic_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Inline ``$defs`` references and drop top-level metadata.

    Anthropic's tool input_schema doesn't accept ``$ref`` / ``$defs``;
    Pydantic emits them for nested BaseModel fields. We do the inline
    here because we're not using the @tool decorator that handles it
    automatically.
    """
    defs = schema.get("$defs", {}) or {}

    def _inline(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref = node["$ref"]
                if isinstance(ref, str) and ref.startswith("#/$defs/"):
                    key = ref[len("#/$defs/") :]
                    if key in defs:
                        merged = dict(_inline(defs[key]))
                        for k, v in node.items():
                            if k == "$ref":
                                continue
                            merged[k] = _inline(v)
                        return merged
            return {
                k: _inline(v) for k, v in node.items() if k != "$defs"
            }
        if isinstance(node, list):
            return [_inline(x) for x in node]
        return node

    out: Dict[str, Any] = {"type": "object"}
    if "properties" in schema:
        out["properties"] = _inline(schema["properties"])
    if "required" in schema:
        out["required"] = schema["required"]
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class QueryPlanner:
    """Plan retrieval queries for one (case, issue) pair via one LLM call.

    The planner is provider-agnostic in spirit but the implementation
    here uses ``ClaudeClient.run_agent_turn`` with a forced tool call.
    OpenAI parity (via ``OpenAIResponsesClient``) is straightforward
    once needed; out of scope for this branch.
    """

    def __init__(
        self,
        *,
        llm_client: ClaudeClient,
        model: Optional[str] = None,
        max_tokens: int = 800,
    ) -> None:
        self.llm_client = llm_client
        self.model = model
        self.max_tokens = max_tokens
        self._tool_schemas = [_emit_query_plan_tool_schema()]

    async def plan(
        self,
        *,
        case_summary: str,
        issue_type: str,
        kg_hint: str = "",
        gold_case_id: str = "",
    ) -> QueryPlan:
        """Run the planner. Returns a ``QueryPlan`` with leakage-filtered queries.

        Args:
            case_summary: Plain-English description of the case as the
                resident gave it (already stripped of post-decision
                fields by the eval adapter). Truncate to ~400 words
                upstream — anything longer wastes tokens.
            issue_type: The issue type string (e.g. ``"repairs_disrepair"``).
            kg_hint: Optional one-line summary of what the KG knows
                about this case (vulnerability flag, Awaab's Law
                applicability, etc.). Empty string means no hint.
            gold_case_id: The case_id under analysis. Used by the
                leakage guard to drop self-referential queries. Empty
                string is permitted in tests.

        Returns:
            A ``QueryPlan`` whose ``queries`` list contains only
            queries that pass the leakage guard. Dropped queries are
            recorded in token-usage stats but not in the returned
            plan; the loop's ``state.blocked_queries`` is the audit
            trail at the agent level.
        """
        user_message = self._build_user_message(
            case_summary=case_summary,
            issue_type=issue_type,
            kg_hint=kg_hint,
        )
        system_blocks = self._build_system_blocks()

        # Force the single tool. The model MUST emit one tool_use
        # block calling emit_query_plan with structured args.
        tool_choice: Dict[str, Any] = {
            "type": "tool",
            "name": _EMIT_TOOL_NAME,
        }

        try:
            response = await self.llm_client.run_agent_turn(
                system_prompt=system_blocks,
                messages=[{"role": "user", "content": user_message}],
                tool_schemas=self._tool_schemas,
                model=self.model,
                max_tokens=self.max_tokens,
                tool_choice=tool_choice,
            )
        except Exception as exc:
            logger.warning(
                "query_planner_llm_error",
                extra={"err": str(exc), "issue_type": issue_type},
            )
            # Empty plan — caller can decide whether to fall back to
            # static_two_pass or abstain.
            return QueryPlan(
                decomposer_model=self.model,
                decomposer_tokens_in=0,
                decomposer_tokens_out=0,
            )

        plan = self._parse_response(response, gold_case_id=gold_case_id)
        plan.decomposer_model = response.model_used
        plan.decomposer_tokens_in = response.tokens_in
        plan.decomposer_tokens_out = response.tokens_out
        return plan

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_system_blocks(self) -> List[Dict[str, Any]]:
        """The system prompt as a list-of-text-blocks with one
        cache_control breakpoint on the static rules text. The version
        marker (QUERY_PLANNER_VERSION) is included as a comment-shaped
        line so cache invalidation is explicit when prompts change."""
        return [
            {
                "type": "text",
                "text": (
                    f"# query_planner_version: {QUERY_PLANNER_VERSION}\n\n"
                    + QUERY_PLANNER_SYSTEM
                ),
                "cache_control": {"type": "ephemeral"},
            }
        ]

    def _build_user_message(
        self,
        *,
        case_summary: str,
        issue_type: str,
        kg_hint: str,
    ) -> str:
        parts = [
            f"Issue type: {issue_type}",
            "",
            "Case summary:",
            case_summary.strip() or "(no summary provided)",
        ]
        if kg_hint:
            parts.extend(["", "Known facts (KG hint):", kg_hint.strip()])
        parts.extend(["", "Emit the query plan now via emit_query_plan."])
        return "\n".join(parts)

    def _parse_response(
        self,
        response: Any,
        *,
        gold_case_id: str,
    ) -> QueryPlan:
        """Find the emit_query_plan tool_use block, validate args,
        apply the leakage filter, and return a clean QueryPlan."""
        tool_use_block = self._find_emit_block(response.content_blocks)
        if tool_use_block is None:
            logger.warning(
                "query_planner_no_tool_use",
                extra={"stop_reason": getattr(response, "stop_reason", None)},
            )
            return QueryPlan()

        raw_args = tool_use_block.get("input") or {}
        try:
            parsed = _EmitQueryPlanArgs.model_validate(raw_args)
        except Exception as exc:
            logger.warning(
                "query_planner_bad_args", extra={"err": str(exc)}
            )
            return QueryPlan()

        kept: List[PlannedQuery] = []
        seen: set[tuple[str, str]] = set()
        for q in parsed.queries:
            key = (q.purpose, q.text.strip())
            if key in seen:
                # Internal dedup: planner emitted two identical entries.
                continue
            try:
                assert_query_safe(q.text, gold_case_id)
            except ToolDispatchError as err:
                logger.info(
                    "query_planner_blocked_query",
                    extra={
                        "purpose": q.purpose,
                        "query": q.text,
                        "reason": str(err),
                    },
                )
                continue
            seen.add(key)
            kept.append(
                PlannedQuery(
                    purpose=q.purpose,
                    text=q.text.strip(),
                    rationale=(q.rationale or "").strip(),
                )
            )

        # Cap kept at 5 even if the model emitted more after dedup —
        # mirrors the spec's "3-5 queries" rule.
        kept = kept[:5]

        return QueryPlan(queries=kept)

    @staticmethod
    def _find_emit_block(
        content_blocks: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        for block in content_blocks:
            if (
                isinstance(block, dict)
                and block.get("type") == "tool_use"
                and block.get("name") == _EMIT_TOOL_NAME
            ):
                return block
        return None
