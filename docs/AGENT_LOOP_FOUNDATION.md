# Agent Loop Foundation

Landed in April 2026 on `feat/agent-loop-foundation`. Plan:
`~/.claude/plans/one-thing-that-i-ve-rustling-finch.md`.

## What's in place

A reusable multi-turn tool-calling loop sits beside the existing
`ClaudeClient`. Everything lives in `packages/llm_orchestrator/agent_loop/`:

- `tool.py` — `@tool` decorator, `Tool`, `ToolSet`, `ToolResult`,
  `UnknownToolError`. Tools are typed sync/async functions with a
  `(ctx: ToolContext, args: BaseModel)` signature.
- `context.py` — `ToolContext` dataclass carrying per-request dependencies
  (rag, kg, storage, ids, trace_logger).
- `loop.py` — `AgentLoop.run(...)` driving the model ↔ tool conversation;
  `AgentTurnClient` Protocol lets us swap scripted clients in tests.
- `trace.py` — `TraceStep`, `TraceSummary`, `TraceLogger` (no-op default),
  `LangFuseTraceLogger` (optional exporter, falls back silently when the
  SDK isn't installed or env vars are missing), and `redact_text` for UK
  PII masking.

`ClaudeClient.run_agent_turn(...)` is the Anthropic adapter for the loop.
The existing `generate` / `generate_structured` / `generate_with_tools`
methods are untouched — nothing in production calls into the agent loop
yet.

A smoke `ToolSet` (`tools/smoke/`: `echo`, `add`) is wired to
`POST /api/dev/agent-smoke`, mounted only when `config.debug` is true.

## What's NOT in place (deliberately)

This branch is foundation only. Follow-up specs to migrate real agents:

1. **Mediator migration**
   Wrap `calculate_zopa`, `calculate_possible_counter_range`, and
   `get_cost_benefit_analysis` as tools. Replace the prompt-only
   `MediatorAgent.generate_opening_message` path with `AgentLoop` so the
   model chooses when to call negotiation helpers. Thread the
   `TraceSummary` back into mediation messages so the UI can render the
   reasoning trail.

2. **Prediction migration**
   Turn `issue_decomposer`, `issue_retrieval`, `issue_predictor`,
   `citation_verifier`, and `output_assembler` into tools. Replace the
   hardcoded Python pipeline in `PredictionEngineV2` with an `AgentLoop`
   run. The glass-box UI gets the richer per-step trace for free.

3. **Streaming**
   Add SSE so `TraceStep`s stream to the frontend as the loop runs.
   Currently the HTTP endpoint blocks until `end_turn`/`max_turns`.

Intake stays on the current prompt-chain path — no plans to migrate.

## Manual verification checklist

The pytest suite covers everything offline. Two manual checks before
shipping migrations on top of this foundation:

1. With `ANTHROPIC_API_KEY` set and `DEBUG=true`:
   ```bash
   uvicorn apps.api.src.main:app --reload
   curl -s -X POST http://localhost:8000/api/dev/agent-smoke \
     -H "content-type: application/json" \
     -d '{"prompt": "add 17 and 25"}' | jq .
   ```
   `final_text` should contain `42`; `trace_summary.steps` should have at
   least a `model_turn → tool_call → model_turn → termination` sequence.

2. With LangFuse env vars set, bring up
   `docker compose -f docker-compose.langfuse.yml up -d`, repeat the curl
   above, and confirm one root trace + one child observation per step in
   the LangFuse UI at `http://localhost:3100`.

## Constraints to preserve

- **Python 3.9.6** — no PEP-604 unions, no `@dataclass(slots=True)`.
- **Tool-to-model payloads stay compact.** Use `trace_payload` for the
  fuller body; the model copy is capped at `max_output_chars`.
- **Per-agent tool sets.** Every migration builds its own `ToolSet` so
  role boundaries hold and prompt injection can't reach across.
- **Cite-or-abstain stays non-negotiable** for any tool that touches
  retrieval. Return IDs and short excerpts, not full documents.
- **LangFuse is optional.** Tests must never depend on it being
  installed or reachable.
