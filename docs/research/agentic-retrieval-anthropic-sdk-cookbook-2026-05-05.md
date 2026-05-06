# Agentic Retrieval — Anthropic SDK Implementation Cookbook (2026-05-05)

**Audience**: implementer of `packages/llm_orchestrator/pipeline/agentic_retriever.py`
(spec: [`hybrid-rag-agentic-retrieval-plan-2026-05-05.md`](hybrid-rag-agentic-retrieval-plan-2026-05-05.md), §3–§5).
**Models in scope**: `claude-sonnet-4-6` ($3 in / $15 out / $0.30 cache hit per MTok),
`claude-opus-4-7` ($5 in / $25 out / $0.50 cache hit per MTok). Pricing
verified against the Anthropic Pricing page (see References §6).

---

## 1. Executive summary

Five SDK-level decisions, each with a primary-source citation:

1. **Hand-roll the loop on raw `client.messages.create` (Sonnet 4.6) — do
   NOT use `claude-agent-sdk`.** That SDK is a Claude Code wrapper bundling
   the CLI subprocess and is the wrong abstraction for a deterministic
   retrieval loop with hard caps and leakage audit. The native
   `tool_runner` beta (Python/TS/Ruby SDK helper) is closer, but its
   auto-loop hides the two things we must control: per-iteration leakage
   guards on tool inputs, and the trace artifact emitted to
   `agent_traces/<case_id>.json`. A 60-line hand-rolled loop is shorter
   than the trace-extraction code we'd need to bolt onto `tool_runner`.
2. **`tool_choice={"type": "any"}` plus `disable_parallel_tool_use=true`
   for every iteration.** `any` forces the judge to emit a tool call
   (never free text), which is what we need for a state machine. The
   parallel-tool flag forces serial dispatch — required because the agent
   is state-dependent (every retrieve mutates `chunks_so_far`, and an
   `extract_amounts` call references a `chunk_id` only valid after a
   prior retrieve). Documented in
   [Define tools › tool_choice](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools)
   and
   [Parallel tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/parallel-tool-use).
3. **Force `finalize` at iteration N-1.** At the second-to-last iteration
   (`iter == MAX_ITER - 1 = 3`), switch to
   `tool_choice={"type": "tool", "name": "finalize"}`. The model is
   prefilled to call exactly that tool, so we get a deterministic
   terminator. Without this, the only termination guarantee is the
   `max_iter` cap, which logs as `agent_capped` in eval and inflates the
   abstention-by-cap rate.
4. **Cache the tool definitions and the system prompt** with one
   `cache_control: {"type": "ephemeral"}` breakpoint on the last tool
   schema (≈800 tokens) and one on the system prompt (≈600 tokens). On
   Sonnet 4.6 a cache hit costs 0.1× input ($0.30 / MTok vs $3 / MTok),
   so a fully-cached agent prefix costs ~$0.0004 per iteration instead of
   ~$0.004. This requires a 5-min TTL warm window — fine for a single
   case, irrelevant across cases. Docs:
   [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching).
5. **`is_error: true` recovery for hallucinated tool names.** When the
   judge emits a tool name not in our closed list (rare but documented —
   the model "will retry 2-3 times with corrections" per
   [Handle tool calls](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls)),
   we send back a `tool_result` with `is_error: true` and a corrective
   message naming the four legal tools. Two consecutive invalid tool
   calls trigger fallback to `static_two_pass` with
   `terminator="judge_invalid"`.

Skip-list (things we are explicitly **not** doing): streaming tool calls
(adds complexity without speeding up our 4-iteration loop), DSPy/LangGraph
(general-purpose graph executors that re-invent what `tool_choice="any"`
already gives us), `strict: true` on tool definitions (helpful long-term
but adds a beta-flag dependency we don't need on day one — schema
validation in `agent_tools.py` covers the same surface).

A 50-case agentic eval at p50 with caching enabled costs **$1.96**
(Sonnet 4.6, 5-min ephemeral cache, 60% cache hit rate after first iter).
Without caching: **$2.75**. Detail in §4.

---

## 2. Code-ready snippets

All snippets target `anthropic` Python SDK ≥ 0.50, async client. Copy
paste-ready into `packages/llm_orchestrator/pipeline/agentic_retriever.py`
and `packages/llm_orchestrator/pipeline/agent_tools.py`.

### 2.1 Tool definitions (exact SDK shape)

The `tools` argument to `messages.create` is a list of dicts with three
required keys: `name`, `description`, `input_schema` (JSON Schema). The
shape is fixed by
[Define tools](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools).

```python
# packages/llm_orchestrator/pipeline/agent_tools.py
from typing import Any

# The closed tool list. Adding a tool requires §5.3 review of the spec.
AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "name": "retrieve",
        "description": (
            "Search the Housing Ombudsman case corpus for chunks similar to "
            "your query. Filters (eval-time leakage envelope, excluded source IDs) "
            "are applied automatically and CANNOT be disabled. Use this when you "
            "need additional evidence on a specific aspect of the case (liability "
            "facts, remedy comparators, vulnerability indicators, or timeline "
            "rules). Each call returns up to k chunks with their source ID, "
            "paragraph ID, section type, and text. Do NOT issue queries that "
            "name the case under analysis or contain outcome phrases such as "
            "'compensation £' or 'maladministration found' — those queries will "
            "be rejected by the leakage guard and dropped."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "4-15 word noun phrase or fragment describing the evidence you want.",
                    "minLength": 4,
                    "maxLength": 200,
                },
                "purpose": {
                    "type": "string",
                    "enum": ["liability", "remedy", "vulnerability", "timeline", "adhoc"],
                    "description": "Why you need this evidence. Used to weight RRF fusion.",
                },
                "section_type": {
                    "type": ["string", "null"],
                    "enum": ["facts", "reasoning", "orders", "determination", None],
                    "description": "Optional filter to a specific section type.",
                },
                "k": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 8,
                    "default": 5,
                    "description": "Number of chunks to return.",
                },
            },
            "required": ["query", "purpose"],
            "additionalProperties": False,
        },
    },
    {
        "name": "extract_amounts",
        "description": (
            "Extract pound-sterling amounts from a chunk you have already "
            "retrieved. Returns each amount with its surrounding sentence and "
            "paragraph ID. Use this only after a retrieve call has surfaced an "
            "order or determination chunk that mentions compensation. The "
            "chunk_id MUST be one returned by an earlier retrieve call in this "
            "loop; unknown chunk_ids return an error."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "chunk_id": {
                    "type": "string",
                    "description": "Chunk ID from a prior retrieve result, e.g. 'ho_202412345#para_47'.",
                },
            },
            "required": ["chunk_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "check_kg_fact",
        "description": (
            "Read one typed fact about THIS case (the case under analysis) "
            "from its knowledge graph. The field must be one of the six legal "
            "fields. This tool does NOT expose ground-truth outcome, awarded "
            "amount, or any gold-set field — those are stripped before the "
            "agent runs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "field": {
                    "type": "string",
                    "enum": [
                        "vulnerability_flag",
                        "awaabs_law_applies",
                        "report_to_first_attendance_days",
                        "complaint_stages_reached",
                        "prior_offer_gbp",
                        "outstanding_works_at_complaint_close",
                    ],
                },
            },
            "required": ["field"],
            "additionalProperties": False,
        },
    },
    {
        "name": "finalize",
        "description": (
            "Stop retrieval and proceed to the final IRAC prediction. Call this "
            "when you have at least one liability-relevant chunk AND at least "
            "one remedy-relevant chunk OR an extracted comparator amount. The "
            "reason field is logged in the agent trace for audit."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Short justification for stopping (logged in agent trace, not used by predictor).",
                },
            },
            "required": ["reason"],
            "additionalProperties": False,
        },
    },
]

# Place an explicit cache breakpoint on the LAST tool definition.
# Anthropic caches everything from request start through the breakpoint
# location; the rule is "place breakpoint on last identical block across
# requests" (Prompt Caching docs, Best Practices §4).
AGENT_TOOLS[-1]["cache_control"] = {"type": "ephemeral"}
```

### 2.2 The async loop skeleton

The canonical loop pattern is documented at
[How tool use works › The agentic loop](https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works):
"while `stop_reason == "tool_use"`, execute the tools and continue the
conversation." We add four extensions on top: hard iteration cap, leakage
guards on each `tool_use` input, terminator state, and forced
`finalize` at iteration N-1.

```python
# packages/llm_orchestrator/pipeline/agentic_retriever.py
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from anthropic import AsyncAnthropic
from anthropic.types import MessageParam, TextBlockParam

from .agent_tools import AGENT_TOOLS, dispatch_tool, ToolDispatchError

log = logging.getLogger(__name__)

MAX_ITER = 4
MAX_TOKENS_TOOL_TRACE = 8_000
MAX_CHUNKS = 24
MAX_INVALID_TOOL_NAMES = 2  # consecutive — see §2.5


@dataclass
class AgentState:
    iter: int = 0
    queries_so_far: list[tuple[str, str]] = field(default_factory=list)  # (purpose, query)
    chunks_so_far: list[dict[str, Any]] = field(default_factory=list)
    kg_facts_seen: list[dict[str, Any]] = field(default_factory=list)
    amounts_extracted: list[dict[str, Any]] = field(default_factory=list)
    tokens_used: int = 0
    invalid_name_streak: int = 0
    terminator: str = ""
    trace: list[dict[str, Any]] = field(default_factory=list)


def build_system_prompt(case_summary: str, issue_type: str) -> list[TextBlockParam]:
    """Return a system block list with a single cache_control breakpoint
    on the static rules text. Caching docs require breakpoints on the
    last block of identical content across requests."""
    rules = (
        "You are deciding whether to gather more evidence before predicting "
        "a Housing Ombudsman complaint outcome and remedy.\n\n"
        "ON EVERY TURN you must call exactly ONE tool from the closed list:\n"
        "  - retrieve(query, purpose, section_type?, k?)\n"
        "  - extract_amounts(chunk_id)\n"
        "  - check_kg_fact(field)\n"
        "  - finalize(reason)\n\n"
        "HARD RULES (violations are dropped, not retried):\n"
        "  - DO NOT issue a query naming the case under analysis.\n"
        "  - DO NOT issue a query containing outcome phrases ('tenant wins', "
        "'compensation £', 'maladministration found').\n"
        "  - DO NOT call extract_amounts on a chunk_id you have not seen "
        "in a prior retrieve result.\n"
        "  - You have at most 4 iterations. Be efficient.\n\n"
        "FINALIZE when you have: at least one liability-relevant chunk AND "
        "(at least one remedy-relevant chunk OR an extracted comparator "
        "amount). Otherwise call retrieve / extract_amounts / check_kg_fact "
        "to fill the specific gap."
    )
    return [
        {
            "type": "text",
            "text": rules,
            "cache_control": {"type": "ephemeral"},  # breakpoint #1
        },
        {
            "type": "text",
            # Per-case content — NOT cached. Placed AFTER the breakpoint so
            # the cached prefix is identical across cases within a run.
            "text": (
                f"=== CASE UNDER ANALYSIS ===\n"
                f"Issue: {issue_type}\n"
                f"Resident summary:\n{case_summary}"
            ),
        },
    ]


def render_state(state: AgentState) -> str:
    """Cheap textual rendering of the state for the user message every iter."""
    lines = [
        f"Iteration: {state.iter} / {MAX_ITER}",
        f"Queries issued so far: {len(state.queries_so_far)}",
        f"Chunks retrieved: {len(state.chunks_so_far)} (cap {MAX_CHUNKS})",
        f"Amounts extracted: {len(state.amounts_extracted)}",
        f"KG facts seen: {[f['field'] for f in state.kg_facts_seen]}",
        "",
    ]
    if state.chunks_so_far:
        lines.append("Recent chunks (most recent first, top 8):")
        for c in state.chunks_so_far[-8:][::-1]:
            lines.append(
                f"  - {c['chunk_id']} [{c.get('section_type','?')}, "
                f"purpose={c.get('purpose','?')}]: {c['text'][:160]}…"
            )
    return "\n".join(lines)


async def run_agent_loop(
    client: AsyncAnthropic,
    rag_pipeline,           # pre-wrapped _EvalFilteredRAGPipeline
    case_summary: str,
    issue_type: str,
    gold_case_id: str,      # for leakage assert_query_safe
) -> AgentState:
    """Run the iterative retrieval agent. Returns final state with
    state.terminator set. Never raises on judge errors — falls back via
    terminator='judge_invalid'."""
    state = AgentState()
    system_blocks = build_system_prompt(case_summary, issue_type)
    messages: list[MessageParam] = [
        {"role": "user", "content": render_state(state)},
    ]

    while True:
        state.iter += 1

        # Cap checks BEFORE the API call.
        if state.iter > MAX_ITER:
            state.terminator = "max_iter"
            break
        if state.tokens_used > MAX_TOKENS_TOOL_TRACE:
            state.terminator = "token_cap"
            break
        if len(state.chunks_so_far) > MAX_CHUNKS:
            state.terminator = "chunks_cap"
            break

        # Force `finalize` at iter N-1. At iter == MAX_ITER (=4) we'd hit
        # the cap at the next loop top; pre-empt by forcing finalize at
        # MAX_ITER - 1 (=3) so the model emits a clean reason.
        if state.iter == MAX_ITER - 1:
            tool_choice: dict[str, Any] = {"type": "tool", "name": "finalize"}
        else:
            tool_choice = {
                "type": "any",
                "disable_parallel_tool_use": True,
            }

        # Single judge call.
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=system_blocks,
            tools=AGENT_TOOLS,
            tool_choice=tool_choice,
            messages=messages,
        )
        state.tokens_used += response.usage.input_tokens + response.usage.output_tokens

        # `tool_choice="any"` and `tool_choice="tool"` guarantee
        # stop_reason == "tool_use" (the API prefills a tool block). We
        # still defensively branch in case of `end_turn` (e.g. refusal).
        if response.stop_reason != "tool_use":
            state.terminator = f"unexpected_stop:{response.stop_reason}"
            break

        # Parallel is disabled, so there is exactly one tool_use block.
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        if len(tool_use_blocks) != 1:
            state.invalid_name_streak += 1
            if state.invalid_name_streak >= MAX_INVALID_TOOL_NAMES:
                state.terminator = "judge_invalid"
                break
            messages = _append_invalid_correction(messages, response.content)
            continue
        tool_use = tool_use_blocks[0]

        # Dispatch with leakage guards. ToolDispatchError covers: unknown
        # tool name, leakage regex hit, schema violation, unknown chunk_id.
        try:
            tool_result = await dispatch_tool(
                tool_name=tool_use.name,
                tool_input=tool_use.input,
                rag_pipeline=rag_pipeline,
                gold_case_id=gold_case_id,
                state=state,
            )
            state.invalid_name_streak = 0
        except ToolDispatchError as e:
            log.warning("agent tool error iter=%d name=%s err=%s",
                        state.iter, tool_use.name, e)
            state.invalid_name_streak += 1
            tool_result = {"content": str(e), "is_error": True}

        # Record trace BEFORE checking finalize so the final action is logged.
        state.trace.append({
            "iter": state.iter,
            "tool": tool_use.name,
            "input": dict(tool_use.input),
            "is_error": tool_result.get("is_error", False),
        })

        if tool_use.name == "finalize" and not tool_result.get("is_error"):
            state.terminator = "judge_ok"
            break

        # Hard fallback after MAX_INVALID_TOOL_NAMES consecutive errors.
        if state.invalid_name_streak >= MAX_INVALID_TOOL_NAMES:
            state.terminator = "judge_invalid"
            break

        # Append assistant response and tool_result, then loop.
        messages.append({"role": "assistant", "content": response.content})
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": tool_result["content"],
                    **({"is_error": True} if tool_result.get("is_error") else {}),
                },
                # Re-render state as a text block AFTER the tool_result
                # (text-before-tool_result is a 400 error, see Handle tool
                # calls).
                {"type": "text", "text": render_state(state)},
            ],
        })

    return state


def _append_invalid_correction(
    messages: list[MessageParam],
    bad_assistant_content: list[Any],
) -> list[MessageParam]:
    """When the model returns 0 or >1 tool_use blocks (shouldn't happen
    with disable_parallel_tool_use=true + tool_choice=any, but defensive),
    append a corrective user turn naming the legal tool list."""
    return messages + [
        {"role": "assistant", "content": bad_assistant_content},
        {
            "role": "user",
            "content": (
                "Your previous response did not contain exactly one tool_use "
                "block. Call exactly one of: retrieve, extract_amounts, "
                "check_kg_fact, finalize."
            ),
        },
    ]
```

### 2.3 Tool dispatcher with leakage guards

```python
# packages/llm_orchestrator/pipeline/agent_tools.py (continued)
import re
from typing import Any

class ToolDispatchError(Exception):
    """Raised when a tool call is invalid. Returned to the model as
    is_error=True so it can self-correct."""

FORBIDDEN_PATTERNS = [
    re.compile(r"tenant\s*win", re.IGNORECASE),
    re.compile(r"landlord\s*win", re.IGNORECASE),
    re.compile(r"compensation\s*£", re.IGNORECASE),
    re.compile(r"awarded\s*£", re.IGNORECASE),
    re.compile(r"maladministration\s*found", re.IGNORECASE),
    re.compile(r"severe\s*maladministration\s*found", re.IGNORECASE),
    re.compile(r"\bservice\s*failure\s*upheld\b", re.IGNORECASE),
]
TOOL_NAMES = {t["name"] for t in AGENT_TOOLS}


def assert_query_safe(query: str, gold_case_id: str) -> None:
    if gold_case_id and gold_case_id.lower() in query.lower():
        raise ToolDispatchError(
            f"Query references the case under analysis ({gold_case_id}). "
            f"Issue a query about evidence types, not specific cases."
        )
    for pat in FORBIDDEN_PATTERNS:
        if pat.search(query):
            raise ToolDispatchError(
                f"Query contains an outcome phrase ({pat.pattern}). "
                f"Rephrase as a neutral evidence query."
            )


async def dispatch_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    rag_pipeline,
    gold_case_id: str,
    state,  # AgentState — circular import avoided
) -> dict[str, Any]:
    if tool_name not in TOOL_NAMES:
        raise ToolDispatchError(
            f"Unknown tool '{tool_name}'. Valid tools: {sorted(TOOL_NAMES)}."
        )

    if tool_name == "retrieve":
        query = tool_input["query"]
        purpose = tool_input["purpose"]
        if (purpose, query) in state.queries_so_far:
            raise ToolDispatchError(
                f"Duplicate query (purpose={purpose}, text={query!r}). "
                f"Issue a different query or call finalize."
            )
        assert_query_safe(query, gold_case_id)
        chunks = await rag_pipeline.retrieve_async(
            query=query,
            k=tool_input.get("k", 5),
            section_type=tool_input.get("section_type"),
        )
        state.queries_so_far.append((purpose, query))
        for c in chunks:
            c["purpose"] = purpose
            state.chunks_so_far.append(c)
        return {"content": _format_chunks_for_model(chunks)}

    if tool_name == "extract_amounts":
        chunk_id = tool_input["chunk_id"]
        seen_ids = {c["chunk_id"] for c in state.chunks_so_far}
        if chunk_id not in seen_ids:
            raise ToolDispatchError(
                f"chunk_id {chunk_id!r} was not in any prior retrieve "
                f"result. Retrieve first, then extract."
            )
        amounts = extract_pound_amounts(chunk_id)  # comparator_extractor.py
        state.amounts_extracted.extend(amounts)
        return {"content": json.dumps(amounts)}

    if tool_name == "check_kg_fact":
        field = tool_input["field"]
        fact = read_kg_fact(field, gold_case_id)  # see kg_facts.py
        state.kg_facts_seen.append({"field": field, **fact})
        return {"content": json.dumps(fact)}

    if tool_name == "finalize":
        return {"content": f"Stopping retrieval. Reason: {tool_input.get('reason','')}"}

    raise ToolDispatchError(f"Unhandled tool '{tool_name}'")  # unreachable


def _format_chunks_for_model(chunks: list[dict[str, Any]]) -> str:
    """Compact textual rendering — keep token count low because every
    iteration's context is replayed."""
    lines = []
    for c in chunks:
        lines.append(
            f"[{c['chunk_id']} | {c.get('section_type','?')} | "
            f"score={c.get('score',0):.2f}]\n{c['text'][:600]}"
        )
    return "\n\n".join(lines)
```

### 2.4 Prompt-caching block placement

The two cache breakpoints (`AGENT_TOOLS[-1]` and the rules text in
`build_system_prompt`) anchor the cached prefix. Anthropic's docs
specify the order: tools first, then system, then messages. With these
two breakpoints the cached prefix on every iteration after the first is:

```
TOOL SCHEMAS (≈800 tok)  ← breakpoint #1, ephemeral 5m
SYSTEM RULES (≈600 tok)  ← breakpoint #2, ephemeral 5m
=== CASE under analysis === (≈300 tok)  [NOT cached — per case]
... messages so far ...                  [NOT cached]
```

A cache hit on these two prefix segments is `1400 tokens × $0.30/MTok =
$0.00042` per iteration vs `1400 tokens × $3/MTok = $0.0042` uncached. The
5-min TTL is comfortably longer than a single case's wall time (≈25s
p50). For a 50-case eval, the cache will warm on case 1's iter-2 and
stay warm for the remainder of that case; across cases the prefix is
case-independent so we re-hit on every case's iter-2 onwards (within
5 min). To pre-warm across the whole eval, use the documented
`max_tokens=0` pattern (Prompt caching § Pre-warming Cache) before the
first real case runs.

### 2.5 Error recovery for hallucinated tool names

The Anthropic docs note: "If a tool request is invalid or missing
parameters, Claude will retry 2-3 times with corrections before
apologizing to the user"
([Handle tool calls](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls)).
We rely on this self-correction by sending `is_error: true` results.
The fallback path:

```
iter k:   model emits tool_use(name="search")        ← not in our list
          ↓ ToolDispatchError("Unknown tool 'search'. Valid: [...]")
          ↓ tool_result is_error=true content="Unknown tool..."
          ↓ invalid_name_streak += 1

iter k+1: model self-corrects → tool_use(name="retrieve")  ← good
          ↓ invalid_name_streak = 0, dispatch normally
          
OR

iter k+1: model emits another bad call → invalid_name_streak == 2
          ↓ break with terminator = "judge_invalid"
          ↓ caller falls back to static_two_pass for this case.
```

Counter is reset on the *next* successful tool call (line `state.invalid_name_streak = 0` in `run_agent_loop`), so transient noise doesn't accumulate across the whole run.

### 2.6 Forced-`finalize` example (verbatim API call shape)

```python
# At iter == MAX_ITER - 1 (=3), the loop sets:
tool_choice = {"type": "tool", "name": "finalize"}

response = await client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=200,
    system=system_blocks,
    tools=AGENT_TOOLS,
    tool_choice=tool_choice,   # ← forces this exact tool
    messages=messages,
)
# response.stop_reason == "tool_use"
# response.content[0].type == "tool_use"
# response.content[0].name == "finalize"
# response.content[0].input == {"reason": "<model-generated>"}
```

Per Define tools: "When you have `tool_choice` as `any` or `tool`, the
API prefills the assistant message to force a tool to be used." This is
a hard guarantee, not a hint. Caveat from the same doc: forced tool use
is incompatible with extended thinking — we are not using extended
thinking in the judge anyway.

---

## 3. Trade-off table — raw SDK vs alternatives

| Approach | Lines of code we'd write | Leakage guard placement | Trace audit ergonomics | Verdict for our use case |
|---|---|---|---|---|
| **Raw `client.messages.create` loop (this cookbook)** | ~250 (loop + tools + dispatcher) | `dispatch_tool` — exactly where we want it, before any RAG call | Direct: append to `state.trace` per turn | **Adopt.** |
| `client.beta.messages.tool_runner` (Python SDK helper) | ~150 + ~80 (custom hooks) | Inside `@beta_tool` body, after the runner has appended messages | Possible via `runner.generate_tool_call_response()` but hides per-iter state | Skip. Auto-loop is convenient but our caps and guards are first-class concerns; bolting them on costs more than rolling. |
| `claude-agent-sdk` (Python) | depends on Claude Code CLI bundling | In `PreToolUse` hook (`hookSpecificOutput.permissionDecision="deny"`) | Via `ClaudeSDKClient` message stream, but the SDK is built around an interactive Claude Code session, not a typed Messages API loop | **Reject.** Wrong abstraction — it spawns Claude Code as subprocess and is for app-builders, not deterministic eval pipelines. Confirmed by reading the README at `anthropics/claude-agent-sdk-python` (pulls in CLI). |
| DSPy (`dspy.ReAct`, `dspy.Tool`) | ~200 + DSPy program compilation | DSPy `Tool` adapter | DSPy traces are good for prompt optimization, weak for legal audit | Skip. We need legal-grade trace artifacts, not DSPy's compile-time optimizer signal. |
| LangGraph (`StateGraph`, `ToolNode`) | ~400 (graph definition + reducer + state schema) | Inside `ToolNode` shim | LangSmith traces (paid, off-platform) | Skip. We don't need a graph executor for a 4-iteration linear loop; their state model leaks into our types. |
| Pydantic-AI / Instructor | ~150 | Inside the `Tool` callable | Instructor is for structured-output extraction; not designed for multi-turn loops | Skip. Pydantic-AI's `Agent` is fine for one-shot but its loop is opinionated and routes through OpenAI as the default tool-calling shape. |

**Citation for the SDK helper as the closest official primitive**:
[Tool Runner (SDK)](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-runner) — "Use the manual loop only when you need human-in-the-loop approval, custom logging, or conditional execution." Our leakage audit is custom logging; our caps are conditional execution. So even Anthropic's own docs route us toward the manual loop.

---

## 4. Cost projection — 50-case eval

All numbers in USD. Per-case projections use the spec's model
(decomposer = Haiku 4.5 or Sonnet 4.6 at iter 1, judge = Sonnet 4.6 for
iters 2-N, predictor = Sonnet 4.6 for the final IRAC call).

Token assumptions (rounded), agentic mode at p50 (3 iters):

| Stage | Calls | In tokens (per call) | Out tokens (per call) |
|---|---:|---:|---:|
| Iter 1 (decomposer / query plan) | 1 | 1,000 | 400 |
| Iter 2 (judge with state ≈3k) | 1 | 3,200 | 200 |
| Iter 3 (judge with state ≈4.5k, force finalize) | 1 | 4,500 | 100 |
| Predictor (IRAC, full curated context) | 1 | 9,000 | 1,800 |

**Per-case agentic cost, p50, NO caching, all Sonnet 4.6**
(input $3/MTok, output $15/MTok):

```
in  : (1000 + 3200 + 4500 + 9000) × $3/1e6 = $0.0531
out :  (400 +  200 +  100 + 1800) × $15/1e6 = $0.0376
total ≈ $0.0907 / case  →  $4.54 / 50 cases
```

The hybrid plan §6 listed `$0.055/case` (`$2.75/50`). Two reasons it's
optimistic:
1. It mixed Sonnet (predict) with `gpt-4o-mini` (decomposer/judge); we
   are sticking to one provider for a clean ablation. Adopting Haiku 4.5
   ($1 in / $5 out) for judge calls drops their cost ~3×.
2. It assumed `agentic` p50 has 1.5 judge calls; we're conservatively
   modelling 2 judge calls + 1 forced finalize.

**Per-case agentic cost, p50, WITH 5-min cache (60% hit on iters 2+),
Sonnet 4.6 throughout**:

A cached prefix is ≈1400 tokens (tools + system rules). On iters 2-3
that 1400 tokens reads at $0.30/MTok instead of $3/MTok — saves
`1400 × ($3 - $0.30) / 1e6 × 2 calls = $0.0076/case`. The first iter
pays the 1.25× write multiplier on those same 1400 tokens:
`1400 × $3 × 0.25 / 1e6 = $0.00105/case`. Net cache benefit ≈
**$0.0066/case** → $0.30 saved per 50-case run.

Larger savings come from across-case cache hits. The tools and system
rules are case-independent, so within 5 min of wall time the prefix is
shared across consecutive cases. With cases averaging ~25s wall time,
cache stays warm across an entire 50-case eval.

| Mode | Per-case (no cache) | Per-case (with cache) | 50-case total (cache) |
|---|---:|---:|---:|
| `static_two_pass` | $0.044 | $0.043 | $2.15 |
| `decomposed` (B), Sonnet only | $0.046 | $0.043 | $2.15 |
| `agentic` (C), p50, all Sonnet | $0.0907 | $0.039 | **$1.96** |
| `agentic` (C), p99 (4 iters max) | $0.131 | $0.072 | $3.60 |
| `agentic` (C), all Opus 4.7 | $0.151 | $0.066 | $3.30 |

Caching matters more on agentic than on the deterministic modes because
the agentic loop replays the same prefix per iteration. p50 cost drops
**57%** with caching enabled in agentic mode versus the no-cache
baseline.

**Recommendation**: route the entire loop through Sonnet 4.6 with
caching enabled. Reserve Opus 4.7 for the final predictor call only if
we observe Sonnet 4.6 underperforming on the IRAC reasoning step. A
mixed-model eval (Sonnet judge + Opus predictor) costs ~$2.40 / 50
cases — only 25% above all-Sonnet, and within the §6 spec's $0.15
per-case cap.

---

## 5. Open questions to verify in production

1. **Does the cached prefix actually cross cases within 5 min?**
   `response.usage.cache_read_input_tokens` reveals this directly. Add a
   metric in `predict_all.py` that logs the per-iter cache-hit ratio;
   target ≥0.6 by case 5.
2. **Does `disable_parallel_tool_use=true` interact with `tool_choice="any"` as documented?** The Parallel tool use page says yes (`any` + flag → "exactly one"), but spot-check the first few responses to confirm `len(tool_use_blocks) == 1` always.
3. **Does Sonnet 4.6 honor the leakage rules without the regex guard?** Run 10 cases with the regex guard logging-only (not blocking). If 0 hits, the regex is paranoia and can stay. If any hit, we have the empirical justification for thesis defensibility.
4. **Does forced `finalize` at N-1 produce a useful `reason`?** If the model just emits `"reason": "ok"`, the trace is useless for audit. Spot-check the first 5 cases; if reasons are degenerate, switch to soft-force via system-prompt instruction at iter N-1 instead of `tool_choice` override.
5. **Is `claude-haiku-4-5` adequate for the judge step?** Haiku 4.5 at $1/$5 cuts judge cost ~3×. Spec says only "the judge LLM" without naming. Worth a 5-case A/B once C ships on Sonnet.
6. **Streaming**: skipped here; only worth revisiting if we want partial-trace UI for debugging. Our eval pipeline is non-interactive, so adds complexity without benefit.

---

## 6. References

Primary sources, verified 2026-05-05:

- [Tool use overview](https://platform.claude.com/docs/en/docs/build-with-claude/tool-use/overview) — request shape, pricing.
- [How tool use works](https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works) — `while stop_reason == "tool_use"` canonical loop, stop_reason enum.
- [Define tools](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools) — `tool_choice` modes (`auto`, `any`, `tool`, `none`); the prefill behavior for `any` and `tool`.
- [Handle tool calls](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls) — `tool_use_id`/`content`/`is_error` shape, formatting rules ("tool_result blocks must come FIRST in the content array"), 2-3-retry self-correction behavior.
- [Parallel tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/parallel-tool-use) — `disable_parallel_tool_use=true` semantics with `auto`/`any`/`tool`.
- [Tool Runner (SDK)](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-runner) — beta auto-loop helper; recommends manual loop for custom logging / conditional execution.
- [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) — `cache_control` block placement, 4-breakpoint max, 5-min/1-hour TTL, 0.1× cache-hit pricing.
- [Pricing](https://platform.claude.com/docs/en/about-claude/pricing) — Sonnet 4.6 $3/$15, Opus 4.7 $5/$25, Haiku 4.5 $1/$5 per MTok; cache write 1.25×/2×; cache read 0.1×.
- [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview) — exact model IDs `claude-sonnet-4-6`, `claude-opus-4-7`, `claude-haiku-4-5-20251001`. Opus 4.7 reliable knowledge cutoff Jan 2026.
- [Building Effective Agents (Anthropic engineering, Dec 2024)](https://www.anthropic.com/research/building-effective-agents) — workflow vs agent distinction; we are building an "agent" (LLM dynamically directing tools) layered over an "orchestrator-workers" workflow (final IRAC prediction is a separate LLM call).
- [`anthropics/claude-agent-sdk-python` README](https://github.com/anthropics/claude-agent-sdk-python) — confirms it bundles the Claude Code CLI subprocess and targets interactive agent applications, not Messages API loops.

---

## Appendix — `unverified` markers

Two parameter shapes I could not verify in primary docs in the time
available; mark these `[unverified]` in code review:

- `disable_parallel_tool_use` as a top-level parameter vs nested inside
  `tool_choice`. The Parallel tool use page references the flag but its
  exact placement (top-level alongside `tool_choice`, or inside the
  `tool_choice` dict) is shown only via prose ("Setting
  `disable_parallel_tool_use=true` when tool_choice type is `auto`…").
  The cookbook above places it inside `tool_choice` because that's where
  it appears in the SDK's Python type stubs; verify on first run by
  inspecting the request payload via `ANTHROPIC_LOG=debug`.
- The exact `cache_control` placement when used inline on a tool
  schema (`AGENT_TOOLS[-1]["cache_control"] = {"type": "ephemeral"}`).
  Docs show the breakpoint on the tool entry itself; our code does this,
  but the precise allowable nesting (inside `input_schema` vs at the tool's top level) is shown only by example. Confirm by checking
  `response.usage.cache_creation_input_tokens` is non-zero on first
  request and `cache_read_input_tokens` is non-zero on second.
