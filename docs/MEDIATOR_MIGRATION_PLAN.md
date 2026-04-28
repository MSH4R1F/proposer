# Phase 2 — Mediator Migration to Agent Loop

## Context

Phase 1 (`feat/agent-loop-foundation`) landed a reusable multi-turn tool-calling loop beside `ClaudeClient`. Nothing in production calls it yet. This phase migrates the first real agent — `MediatorAgent` — from a prompt-chain that pre-computes ZOPA/cost-benefit in Python to an `AgentLoop` where the model chooses when to call those helpers. The trace becomes a first-class part of the mediation message, so the UI can render the reasoning trail next to each mediator reply.

**Branch:** `feat/mediator-migration` off `origin/main` (`b8a923c`), worktree at `../legal-mediation-system-mediator`.

Goal order (same as foundation): transparency > autonomy > maintainability.

## Scope

**In scope**
- `MEDIATOR_TOOLS` tool set wrapping `calculate_zopa`, `calculate_counter_range`, `get_cost_benefit` as `@tool` decorators. Pure Python, no LLM calls inside tools.
- Replace both `MediatorAgent.generate_opening_message(...)` and `MediatorAgent.generate_response(...)` with `AgentLoop.run(...)` calls.
- Extend `ToolContext` with the per-mediation fields the tools need (`prediction`) so tools pull deterministic facts from context, not from model args.
- Extend `MediationMessage` with an optional `reasoning_trace: Optional[TraceSummary]` field. Persisted in the session JSON file alongside the message. Round-trips via the existing `GET /api/mediation/{dispute_id}/messages` endpoint.
- Frontend: new `MediatorReasoningTrail.tsx` collapsible component, rendered under each `ai_mediator` message bubble.
- Tests: scripted `AgentTurnClient` drives the new paths; a round-trip test for trace persistence; existing `test_mediation.py` continues to pass (adjusted expectations where trace fields appear).

**Out of scope (later phases)**
- Prediction pipeline migration.
- SSE streaming of `TraceStep`s.
- Intake agent changes.
- Schema changes to `DisputeCase` or the dispute-service persistence model.

## Locked Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Data injection for tools | Via `ToolContext` fields, not tool args | Model can't mutate deterministic facts; smaller token footprint; no exposed prediction schema |
| Tool granularity | Three tools mirroring existing methods 1:1 | Preserves the exact deterministic calculations; model chooses ordering, not math |
| Opening + response both migrate | Yes | Half-migration leaves traces inconsistent, UI logic forks |
| Trace storage | `MediationMessage.reasoning_trace` (optional `TraceSummary`) | Minimal model surface change, trace already a Pydantic model, persists with the session JSON |
| Trace exposure | Comes back with `GET /messages` automatically | No new endpoints; frontend reads the existing response |
| UI rendering | Collapsible panel under each mediator bubble, hidden by default | Non-intrusive, power users can expand, LangFuse is for deeper dives |
| System prompt | Rewrite from scratch for tool-use framing | Old prompt hand-fed ZOPA as text; new prompt explains the tools and when to call them |
| Voice/tone | Carry forward the conversational "calm neutral, 2-4 sentences, plain prose, no markdown" style from the existing refinement direction | Keeps the UX consistent with where the product is heading |
| Model autonomy cap | `max_turns=6` for opening, `max_turns=8` for response | Opening is deterministic enough for ≤6 turns; response may need 2–3 tool rounds |

## Architecture

```text
MediationService.start_mediation(...)
    │
    ▼
MediatorAgent.generate_opening_message(...)
    │  builds ToolContext(prediction=..., dispute_id=..., session_id=..., trace_logger=...)
    │  AgentLoop(claude_client, MEDIATOR_TOOLS).run(system, messages, ctx)
    ▼
AgentLoop                                        ┌─ calculate_zopa(ctx)        → reads ctx.prediction
    ├── model_turn: "I need ZOPA"                │    returns compact payload, caches trace_payload
    ├── tool_call: calculate_zopa ───────────────┤
    ├── model_turn: "OK, reply text"             ├─ calculate_counter_range(ctx, CounterArgs)
    └── termination: END_TURN                    │
                                                  └─ get_cost_benefit(ctx, CostBenefitArgs)
    returns (final_text, TraceSummary)
    │
    ▼
MediatorAgent persists MediationMessage(content=final_text, reasoning_trace=summary)
    │
    ▼
GET /api/mediation/{dispute_id}/messages   → frontend receives trace alongside message
    │
    ▼
<MediatorReasoningTrail trace={msg.reasoning_trace} /> (collapsed by default)
```

### Tool contracts

```python
class ZopaArgs(BaseModel):
    """No args — read prediction from context."""
    pass

@tool(description="Calculate the Zone of Possible Agreement from the dispute's prediction. Returns {min, max, center} in GBP.")
def calculate_zopa(ctx: ToolContext, args: ZopaArgs) -> dict[str, float]:
    ...

class CounterArgs(BaseModel):
    current_offer: float = Field(..., description="The offer on the table, in GBP.")
    role: Literal["tenant", "landlord"] = Field(..., description="Which side would propose the counter.")

@tool(description="Given a current offer and which party is responding, return the range of fair counter-offers that lie within ZOPA.")
def calculate_counter_range(ctx: ToolContext, args: CounterArgs) -> dict[str, float]:
    ...

class CostBenefitArgs(BaseModel):
    role: Literal["tenant", "landlord"]

@tool(description="Return the role-specific settlement-vs-tribunal cost-benefit framing for the mediation.")
def get_cost_benefit(ctx: ToolContext, args: CostBenefitArgs) -> dict[str, Any]:
    ...
```

Why `ZopaArgs` is empty: the model shouldn't re-supply the prediction it was just told about — it would either paraphrase or hallucinate numbers. The tool reads `ctx.prediction` and the result is deterministic.

### `ToolContext` extension

```python
@dataclass
class ToolContext:
    # existing fields...
    prediction: Optional[PredictionResult] = None  # NEW
```

`cost_benefit_cache` is intentionally not a context field — `get_cost_benefit` recomputes from `ctx.prediction` each call (cheap, static data).

### Trace persistence

`MediationMessage.reasoning_trace: Optional[TraceSummary] = None`. `TraceSummary` is already a Pydantic model → serializes into the session JSON without changes. Only mediator messages get a populated trace; tenant/landlord/system messages leave it `None`.

The existing `GET /api/mediation/{dispute_id}/messages` returns `MediationMessage` models, so the trace rides along automatically.

## Guardrails

- Tools stay deterministic (no LLM calls inside them). Matches Phase 1 guardrail.
- Prediction data must flow through context, never be re-supplied as args.
- System prompt never contains ZOPA numbers, cost tables, or cases — the model calls tools to get them. Keeps prompt short and forces the glass-box pattern.
- Trace persistence only stores the compact `TraceSummary`, not per-tool `trace_payload` bodies (those live only in LangFuse). Prevents the session JSON from ballooning.
- `test_mediation.py` must stay green. The new trace field is optional, so serialization stays compatible; assertions that care about message content need no change.

## Critical files

**New**
- `packages/llm_orchestrator/tools/mediator/__init__.py` — exports `MEDIATOR_TOOLS`
- `packages/llm_orchestrator/tools/mediator/calculate_zopa.py`
- `packages/llm_orchestrator/tools/mediator/calculate_counter_range.py`
- `packages/llm_orchestrator/tools/mediator/get_cost_benefit.py`
- `packages/llm_orchestrator/tests/test_mediator_tools.py`
- `packages/llm_orchestrator/tests/test_mediator_agent_loop.py`
- `apps/web/components/mediation/MediatorReasoningTrail.tsx`
- `apps/web/lib/types/trace.ts`

**Modified**
- `packages/llm_orchestrator/agent_loop/context.py` — add `prediction` field
- `packages/llm_orchestrator/agents/mediator_agent.py` — both flows use `AgentLoop`; return tuple `(text, TraceSummary)`
- `packages/llm_orchestrator/prompts/mediator.py` — new system prompt with tool-use framing + conversational voice
- `packages/llm_orchestrator/models/mediation.py` — add optional `reasoning_trace` to `MediationMessage`
- `apps/api/src/services/mediation_service.py` — thread trace into the persisted message
- `apps/web/lib/types/mediation.ts` — add `reasoning_trace` to message type
- `apps/web/components/mediation/MediationMessageBubble.tsx` (where mediator bubbles render) — render the reasoning trail component

**Reused (no change)**
- `packages/llm_orchestrator/agent_loop/loop.py`, `tool.py`, `trace.py`
- `packages/llm_orchestrator/clients/claude_client.py` (uses `run_agent_turn` as-is)
- `packages/llm_orchestrator/data/tribunal_costs.py` (the underlying helper)

## Implementation Plan

Ten discrete commits. Each one is self-contained and its own subagent dispatch + two-stage review per `superpowers:subagent-driven-development`.

### Step 1 — Extend `ToolContext` with `prediction` field

Add `prediction: Optional[PredictionResult] = None` to `ToolContext`. Import lazily via `TYPE_CHECKING` so `agent_loop` stays free of the orchestrator-model cycle. Update `test_tool_context.py` with a single assertion.

**Commit:** `feat(agent-loop): add prediction field to ToolContext`

### Step 2 — Add optional `reasoning_trace` field to `MediationMessage`

Extend `MediationMessage` in `models/mediation.py` with `reasoning_trace: Optional[TraceSummary] = None`. Confirm session JSON round-trips via a new test in `test_mediation.py` (or a dedicated `test_mediation_models.py`). No changes to existing messages — field is optional.

**Commit:** `feat(mediation): add optional reasoning_trace to MediationMessage`

### Step 3 — Three mediator tools + `MEDIATOR_TOOLS` set

Create `tools/mediator/` with the three tools above. Each tool is a thin wrapper over the existing pure methods on `MediatorAgent` — lift the calculation into a module-level function and `@tool`-decorate it. `MediatorAgent.calculate_zopa`, `calculate_possible_counter_range`, `calculate_zopa_proxy` can either remain as methods delegating to the module functions, or be removed once the agent no longer uses them directly (Step 5 decides). Test file covers schema shape, happy path per tool, and `ToolSet` registration.

**Commit:** `feat(mediator): add calculate_zopa, calculate_counter_range, get_cost_benefit tools`

### Step 4 — Rewrite mediator system prompt for tool-use

Replace `MEDIATOR_SYSTEM_PROMPT` with a new prompt that:
- Introduces the three tools and when to call each.
- Keeps the conversational voice: calm neutral, 2–4 sentences, plain prose, no markdown.
- Forbids fabricated case citations (reinforces foundation guardrail).
- Explains that ZOPA / cost-benefit numbers must come from tool calls, never guessed.

Remove `MEDIATOR_OPENING_USER_PROMPT` / `MEDIATOR_RESPONSE_USER_PROMPT` templates — the new flow builds the user-turn content from dispute context + recent messages directly.

**Commit:** `feat(mediator): rewrite system prompt for agent-loop tool-use`

### Step 5 — Migrate `generate_opening_message` to `AgentLoop`

`MediatorAgent.generate_opening_message(...)` now:
1. Builds `ToolContext(prediction=..., dispute_id=..., trace_logger=...)`.
2. Constructs a single user message that describes the dispute + expectation data (no pre-computed ZOPA).
3. Runs `AgentLoop(self.llm, MEDIATOR_TOOLS, max_turns=6).run(system, messages, ctx)`.
4. Returns a tuple `(final_text, TraceSummary)`.

Callers in `mediation_service.py` update to receive the tuple.

Scripted `AgentTurnClient` test: opener calls ZOPA tool, then replies. Asserts final text + trace shape.

**Commit:** `feat(mediator): migrate generate_opening_message to AgentLoop`

### Step 6 — Migrate `generate_response` to `AgentLoop`

Same pattern. `max_turns=8`. User-turn content includes the last ~12 messages, the latest offer (if any), and dispute context. The model chooses whether to call `calculate_counter_range` / `get_cost_benefit` based on what the offer/thread calls for.

Scripted test: offer on table → model calls `calculate_counter_range` + `get_cost_benefit` → replies with a conversational response.

**Commit:** `feat(mediator): migrate generate_response to AgentLoop`

### Step 7 — Persist trace through `MediationService`

Update `MediationService` call sites (`start_mediation`, the message-handling path where `generate_response` fires) to receive the tuple and write `reasoning_trace` onto the `MediationMessage` before it's saved. The existing `GET /messages` endpoint exposes it automatically.

Regression-test the existing `test_mediation.py` suite — any assertion that looked at message serialization shape should still pass because the field is optional.

**Commit:** `feat(mediation): persist reasoning trace with mediator messages`

### Step 8 — Frontend: types + `MediatorReasoningTrail` component

- `apps/web/lib/types/trace.ts` — TypeScript mirrors of `TraceStep` / `TraceSummary`.
- `apps/web/lib/types/mediation.ts` — extend `MediationMessage` with optional `reasoning_trace`.
- `apps/web/components/mediation/MediatorReasoningTrail.tsx` — collapsible `<details>` panel showing step index, kind, name, duration. Hidden by default.
- Wire the component into the existing chat bubble renderer (`apps/web/components/mediation/MediationMessageBubble.tsx`).

Type-check must pass; no new runtime dependencies.

**Commit:** `feat(web): render mediator reasoning trail under mediator messages`

### Step 9 — End-to-end smoke + regression sweep

Verification gate, no commit:
- Run the focused new tests first.
- `pytest packages/llm_orchestrator/tests apps/api/tests` — full suite green.
- Manually: `DEBUG=true uvicorn apps.api.src.main:app --reload` → trigger a mediation start via the existing dispute flow → confirm the opening message has a populated `reasoning_trace` in the `/messages` response.
- If LangFuse is up, confirm the trace appears there too.

### Step 10 — Commit plan doc + update foundation completion note

- Commit this plan file.
- Add a short section to `docs/AGENT_LOOP_FOUNDATION.md` crossing off "Mediator migration" in the deferred list.
- Handoff note for the next contributor: Phase 3 (prediction migration) is still ahead.

**Commit:** `docs: record mediator migration plan and update foundation handoff`

## Rollback

Each step is additive except Steps 5–7 which replace method bodies. If any step needs to be reverted:
- Steps 1–4, 8: drop the new modules / revert single-field additions.
- Steps 5–7: revert `mediator_agent.py` + `mediation_service.py` to the pre-step versions; old prompt templates live in Step 4's diff if needed.

The foundation branch's behavior is untouched throughout — no existing call sites change in Phase 1 scope.

## Verification

**Unit (offline):**
- Each tool returns the expected schema and value on representative inputs.
- `ToolSet` registers all three without name collisions.
- `MediationMessage` with `reasoning_trace` round-trips via `model_dump` / `model_validate`.
- `generate_opening_message` and `generate_response` return `(str, TraceSummary)`; trace steps include the expected tool calls.
- Existing `test_mediation.py` passes.

**Manual (opt-in, needs API key):**
- Start a dispute, run it through prediction, start mediation, confirm the mediator's first message has a non-empty trace with at least one `calculate_zopa` tool call.
- Submit a counter-offer, confirm the mediator's response trace includes `calculate_counter_range` and possibly `get_cost_benefit`.
- LangFuse UI shows one trace per mediator turn with per-tool observations.

## Follow-ups (not this phase)

- **Prediction migration**: turn the 5 prediction pipeline steps into tools.
- **SSE streaming**: stream `TraceStep` events to the frontend as the loop runs.
- **Trace retention policy**: decide if/when old traces get pruned from session JSON.
