# Agentic Retrieval — Implementation Handoff (2026-05-06)

**Branch**: `feature/agentic-retrieval` (off `feature/housing-ombudsman-live-eval` at commit `9082eeb`)
**Last commit**: `0a57042` — `feat(claude_client): tool_choice + cached system prompt for agent turns`

This doc tells the next session **exactly** where to pick up. All
deterministic code is committed and tested. What's left is the LLM
loop, the engine wiring, and the smoke test.

## Reading order before writing code

1. `docs/research/hybrid-rag-agentic-retrieval-plan-2026-05-05.md` — overall spec (B and C)
2. `docs/research/agentic-retrieval-anthropic-sdk-cookbook-2026-05-05.md` §2.2-§2.6 — paste-ready loop skeleton, error recovery, forced finalize
3. `docs/research/agentic-retrieval-architecture-research-2026-05-05.md` §3.1-§3.4 — state-machine pseudocode, judge prompt, termination policy, trace schema
4. This file — what's actually built and what's left.

## What's built (5 commits on the branch)

| Commit | What it added | Tests |
|---|---|---:|
| `11f13f2` | Investigation deliverables: master plan + research × 4 + index | — |
| `630c7fc` | SDK cookbook + architecture research | — |
| `8b44429` | Foundation: trace enum extension, comparator_extractor, agent_state models | 27 + 16 = 43 |
| `2a01b72` | 5 tools (retrieve / extract_amounts / check_kg_fact / finalize / abstain) + leakage guards + agent_prompts | 38 |
| `0a57042` | `ClaudeClient.run_agent_turn` extension: `tool_choice` + cached `system` block list | (existing 22 unaffected) |

**Total**: 94 passing tests (`pytest packages/llm_orchestrator/tests/`). No existing tests modified.

### Code surface that exists

```
packages/llm_orchestrator/
├── agent_loop/
│   └── trace.py         (extended: 7 new TraceTerminationReason values)
├── clients/
│   └── claude_client.py (extended: tool_choice + cached system blocks)
├── models/
│   └── agent_state.py   (NEW: AgentState, AgentChunk, AgentAmount,
│                              AgentKGFact, AgentAction, PlannedQuery,
│                              QueryPlan)
├── pipeline/
│   ├── comparator_extractor.py (NEW: extract_pound_amounts, ExtractedAmount)
│   └── retrieval_agent_tools.py (NEW: 5 @tool defs, RetrievalToolContext,
│                                       assert_query_safe, FORBIDDEN_PATTERNS,
│                                       build_retrieval_toolset)
├── prompts/
│   └── agent_prompts.py (NEW: QUERY_PLANNER_SYSTEM, SUFFICIENCY_JUDGE_SYSTEM,
│                              render_state_for_judge)
└── tests/
    ├── test_agent_state.py             (16 tests)
    ├── test_comparator_extractor.py    (27 tests)
    └── test_retrieval_agent_tools.py   (38 tests, incl. envelope-inheritance proxy)
```

### Key invariants already enforced in code

- **Leakage**: `assert_query_safe` blocks queries that name the gold case_id or contain outcome-revealing phrases (FORBIDDEN_PATTERNS). Blocked queries are logged on `state.blocked_queries` for the trace audit (`plan §5.4`). The dispatcher rejects the query *before* any RAG call.
- **Cycle guard**: `state.has_query(purpose, query)` rejects duplicates. Dedup of chunks happens on insert via `state.add_chunks` keyed on `(source_id, paragraph_id)`.
- **Closed tool list**: 5 tools, each with a Pydantic args model. KG field reads are restricted to a closed enum (no ground-truth fields). `extract_amounts` rejects unknown chunk_ids.
- **No raw RAG construction**: `retrieve` calls `ctx.rag.retrieve(...)` — the engine wraps the RAG in `_EvalFilteredRAGPipeline` upstream, so envelope filters are inherited.

## What's left (4 chunks, ~12-16 dev-hours)

### Chunk A — `retrieval_agent_loop.py` (the main piece)

**File to create**: `packages/llm_orchestrator/pipeline/retrieval_agent_loop.py`

**Spec**: cookbook §2.2 has the full async loop. Architecture research §3.1 has the state-machine pseudocode. The loop should:

1. Take `case_file`, `issue_context`, `rag` (already-wrapped), `kg`, `llm_client`, `gold_case_id` and return an `AgentState`.
2. **Iteration 1 (Architecture B)**: call a `QueryPlanner` (next chunk down) to get a `QueryPlan`; run all queries in parallel via `asyncio.gather`; populate `state.chunks_so_far`. Increment `state.iter`.
3. **Iterations 2..MAX_ITER**: build the user message via `render_state_for_judge(state)`; build the system prompt as a list-of-text-blocks with one `cache_control: ephemeral` breakpoint on the static `SUFFICIENCY_JUDGE_SYSTEM` text; call `client.run_agent_turn(...)` with:
   - `tool_choice = {"type": "any", "disable_parallel_tool_use": True}` for iters 2..MAX_ITER-2
   - `tool_choice = {"type": "tool", "name": "finalize"}` at iter MAX_ITER-1 (=3)
4. Dispatch the returned tool_use block via `RETRIEVAL_TOOLSET.dispatch(name, args, ctx)`. Append tool_result to messages.
5. Termination paths (in priority order — see architecture research §3.3):
   - `finalize` returned with `confidence_score >= 0.70` → `JUDGE_OK`
   - `finalize` returned with `confidence_score < 0.70` → keep iterating subject to caps
   - `abstain` returned → `JUDGE_ABSTAIN`
   - `dup_query` raised by retrieve → `DUP_QUERY`
   - 2 consecutive invalid tool calls → `JUDGE_INVALID` (fall back to static_two_pass at caller side)
   - `state.tokens_used > MAX_TOKENS_TOOL_TRACE (8000)` → `TOKEN_CAP`
   - `len(state.chunks_so_far) > MAX_CHUNKS (24)` → `CHUNKS_CAP`
   - `state.iter >= MAX_ITER (4)` reached → `MAX_ITER`

**Constants** (per spec — copy from cookbook):

```python
MAX_ITER = 4
MAX_TOKENS_TOOL_TRACE = 8_000
MAX_CHUNKS = 24
MAX_INVALID_TOOL_NAMES = 2  # consecutive
JUDGE_CONFIDENCE_THRESHOLD = 0.70
```

**Tests to write** (mock the LLM client with a scripted fake — see `packages/llm_orchestrator/tests/test_agent_loop.py` for the existing fake-client pattern):

- `test_iter1_planner_runs_first` — iter 1 calls planner, populates chunks, no judge call yet
- `test_finalize_with_high_confidence_terminates_judge_ok` — judge emits `finalize(confidence=0.85)` → terminator=JUDGE_OK
- `test_finalize_with_low_confidence_keeps_iterating` — judge emits `finalize(confidence=0.55)` → another judge turn happens
- `test_abstain_terminates_judge_abstain`
- `test_dup_query_terminates` — judge emits same `(purpose, query)` twice
- `test_max_iter_cap` — judge always retrieves → terminator=MAX_ITER
- `test_token_cap_short_circuits` — pre-load state with tokens_used > 8k → terminator=TOKEN_CAP without further calls
- `test_chunks_cap_short_circuits`
- `test_invalid_tool_name_recovery` — judge emits unknown tool once, recovers next turn
- `test_two_consecutive_invalid_terminates_judge_invalid`
- `test_forced_finalize_at_iter_n_minus_1` — at iter 3 the request payload contains `tool_choice={"type":"tool","name":"finalize"}`
- `test_blocked_query_logged_in_audit_not_rethrown` — bad query is rejected, agent self-corrects, audit list grows

### Chunk B — `query_planner.py`

**File to create**: `packages/llm_orchestrator/pipeline/query_planner.py`

**Spec**: small module, ~150 LOC.

```python
class QueryPlanner:
    def __init__(self, llm_client, model: str = "claude-sonnet-4-6"): ...

    async def plan(
        self,
        *,
        case_file: CaseFile,
        issue: IssueContext,
        kg: Optional[KnowledgeGraph],
        gold_case_id: str = "",
    ) -> QueryPlan:
        """One LLM call. System: QUERY_PLANNER_SYSTEM. User: case
        summary + issue type + KG hint. Force JSON output via
        Pydantic-validated parse. Run assert_query_safe on each
        emitted query before returning; drop violators and log to a
        plan-side ``blocked_queries`` field (mirrors the loop's audit
        path)."""
```

Use `client.generate(...)` (not `run_agent_turn` — no tools needed; just structured JSON). Output schema follows the `QueryPlan` model in `models/agent_state.py`.

**Tests**:
- `test_plan_emits_at_least_one_remedy_query` — using a scripted client returning a 4-query plan
- `test_plan_filters_outcome_phrase_queries` — scripted client returns a plan with a forbidden query → result has 1 blocked + 3 kept
- `test_plan_handles_invalid_json` — scripted client returns malformed JSON → caller gets an empty `QueryPlan` with a `parse_error` field (or raises a typed error — design choice)

### Chunk C — Wire `AGENTIC` mode into `prediction_engine_v2.py`

**File to modify**: `packages/llm_orchestrator/pipeline/prediction_engine_v2.py:89-279`

**Changes**:
1. Add `RetrievalMode` enum to `models/prediction_v2.py` if not already there: `STATIC`, `STATIC_TWO_PASS`, `DECOMPOSED`, `AGENTIC`.
2. In `PredictionEngineV2.__init__`, accept `retrieval_mode: RetrievalMode`.
3. After the existing per-issue retrieval branch (lines 199-204), add a guard: if `retrieval_mode == AGENTIC`, replace `IssueRetriever.retrieve_all` with a call to `RetrievalAgentLoop.run(...)` per issue, then convert the resulting `AgentState.chunks_so_far` into `IssueRetrievalResult` shape so the downstream `IssuePredictor` is unchanged.
4. Persist the `AgentState.trace` (or a serialised `AgentTrace` model) into the prediction artifact via `predict_all.py:_serialise_prediction` (the existing `verifier_hash` field shows where to extend).

**Tests**: extend `packages/llm_orchestrator/tests/test_prediction_engine_v2.py` (or create one if absent) with a single integration test that mocks both planner and judge to return scripted responses, verifies the chunks reach the predictor.

### Chunk D — Smoke test on a fixture case

**Goal**: end-to-end run of mode AGENTIC on one real Ombudsman case from `data/gold_standard/housing_repairs_social_v1.jsonl`. Verify:
- Agent trace has at least 2 iterations
- `terminator ∈ {JUDGE_OK, JUDGE_ABSTAIN}`
- `leakage_audit.all_queries_filter_applied is True`
- No `blocked_queries` (or all of them are sensible)
- A prediction is produced (winner, amount, supporting_cases)

Use `housing-ombudsman-202428538` (gold £3818, hybrid £400 — the worst amount-band miss in the failure taxonomy) as the smoke fixture. If C is doing its job, the agent should at least retrieve some orders/determination chunks and extract `£3818` (or comparable amounts from similar cases) for the predictor.

```bash
PYTHONPATH=packages venv/bin/python scripts/eval/predict_all.py \
  --gold data/gold_standard/housing_repairs_social_v1.jsonl \
  --out-dir eval/predictions/agentic_smoke_$(date +%Y%m%d_%H%M%S) \
  --engine live --client openai \
  --modes agentic \
  --retrieval-mode agentic \
  --limit 1 \
  --case-id housing-ombudsman-202428538 \
  --rag-index-root indices --top-k 5
```

(Add `--retrieval-mode` and `--case-id` CLI flags during Chunk C wiring.)

## Open issues to resolve during implementation

1. **`disable_parallel_tool_use` placement**: cookbook §Appendix flags this as `[unverified]` — top-level vs nested in `tool_choice` dict. SDK Python type stubs put it inside `tool_choice`. Verify on first live call by inspecting request payload via `ANTHROPIC_LOG=debug`.
2. **`cache_control` on tool entries**: the cookbook places `cache_control: ephemeral` on the LAST tool definition (`AGENT_TOOLS[-1]["cache_control"] = ...`). Verify `response.usage.cache_creation_input_tokens` is non-zero on first request and `cache_read_input_tokens` non-zero on second.
3. **Judge `confidence_score` calibration**: the architecture research recommends τ=0.70 from EviMem ρ=0.93 evidence. Re-check on first 50 cases. If post-eval ECE > 0.10, apply temperature scaling (F-CAL-1 in the master plan) to the judge's confidence before trusting τ.
4. **Forced-finalize `reason` quality**: cookbook §5 open question 4 — if the model just emits `"reason": "ok"` at iter N-1, the trace is useless for audit. Spot-check the first 5 cases.

## Pricing reminder (corrected from the original plan)

| Model | Input $/MTok | Output $/MTok | Cache hit $/MTok |
|---|---:|---:|---:|
| Sonnet 4.6 | $3 | $15 | $0.30 |
| Opus 4.7 | **$5** | **$25** | $0.50 |
| Haiku 4.5 | $1 | $5 | $0.10 |

The original agentic plan had Opus at $15/$75 — that's Opus 4.1's old pricing. Cookbook §1 has the corrected numbers and a $1.96 / 50-case projection at p50 with caching.

## Related Linear tickets (for tracking)

The master plan §3 names these IDs; create them on Linear before
implementation, in this order:

- `F-AGENT-2`: tool framework + leakage guards (DONE in commit `2a01b72`)
- `F-AGENT-3`: comparator extractor (DONE in commit `8b44429`)
- `F-AGENT-1`: QueryPlanner module (Chunk B)
- `F-AGENT-4`: agentic_retriever state machine + judge loop (Chunk A)
- `F-AGENT-5`: trace persistence + audit step (Chunks A + C)
- `F-AGENT-6`: 5-case smoke vs `static_two_pass` and `decomposed` (Chunk D smoke)
- `F-AGENT-7`: full 50-case eval + promote-or-deprecate gate

Phase 1 prerequisites (`F-EVAL-1`, `F-EVAL-2`, `F-CAL-1`, `F-AMT-1`, `F-MODE-1`) from the master plan are blocking the *thesis-defensible* eval, not the *runnable* smoke. Run smoke first; honest comparison metrics need Phase 1.

## What is *not* in scope for this branch

- Phase 1 prerequisites (split into a separate branch).
- Architecture B as a standalone mode (subsumed by C's iter 1 — split out only if we deprecate C and ship B alone).
- Cross-case prompt-cache pre-warming.
- Langfuse self-host setup (the trace artifact format is OTel-aligned but the Langfuse server itself is separate ops).
- Mixed-model agent loops (Sonnet judge + Opus predictor) — defer until C ships on Sonnet end-to-end.
- The within-band CQR amount predictor (F-AMT-2 in master plan) — separate ticket, can land in parallel.
