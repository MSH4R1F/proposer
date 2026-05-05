# Agentic Retrieval Implementation Plan (2026-05-05)

**Status**: Ticket-ready plan for B (single-shot query decomposition) and C
(iterative retrieval agent), to be implemented after the Tier-1 quick wins
in [`hybrid-rag-improvement-plan-2026-05-05.md`](hybrid-rag-improvement-plan-2026-05-05.md)
(F-EVAL-1, F-EVAL-2, F-RET-2, F-CAL-1, F-MODE-1, F-PROMPT-2) land.
**Companion**: extends Tier 2/3 of the master plan; does not replace it.

This doc adds two new techniques on top of the deterministic two-pass
retrieval (F-RET-1) already on the roadmap. C *uses* B as its first
iteration, so they share most of the implementation surface.

---

## 1. Decision summary

We add two retrieval modes alongside the existing static retrieval:

| Mode id | Name | LLM calls / case | When the LLM picks queries | When to use |
|---|---|---:|---|---|
| `static` (existing) | Single-blob query | 1 | never | baseline |
| `static_two_pass` (F-RET-1) | Liability + remedy hardcoded passes | 1 | never | baseline+ |
| `decomposed` (**B**, F-AGENT-1) | LLM emits N queries once, parallel retrieval | 2 | once, before retrieval | adapts to weird cases without an agent loop |
| `agentic` (**C**, F-AGENT-2..5) | Iterative retrieve→judge→retrieve loop | 3-6 | every iteration | multi-hop / unknown taxonomy |

C is implemented as B + a sufficiency judge + an iteration loop; you build
B first, then layer C on top using the same tool primitives.

**Headline tradeoffs**:
- B costs +1 cheap LLM call (≈$0.001 per case at GPT-4o-mini prices), buys
  query adaptiveness, keeps a clean ablation story.
- C costs +2 to +5 LLM calls, buys multi-hop reasoning, makes ablation
  combinatorial. Bound it hard: max 4 iterations, max 24 cumulative chunks,
  max 8k tool-trace tokens.
- Both rely on the existing `_EvalFilteredRAGPipeline` envelope
  ([scripts/eval/predict_all.py:196-213](../../scripts/eval/predict_all.py:196))
  so leakage filters are inherited by *every* tool call automatically.
  This is the single most important invariant — see §5.

---

## 2. Architecture B — single-shot query decomposer

**Goal**: replace the single-blob query in
[issue_retrieval.py:546-597](../../packages/llm_orchestrator/pipeline/issue_retrieval.py:546)
with N adaptive queries planned by an LLM, run in parallel, fused with RRF.
Stays deterministic at runtime (one decomposer call, parallel retrieves,
no loops).

### 2.1 Mechanism

Per case, per issue:

1. Call cheap-LLM (Haiku 4.5 or GPT-4o-mini) once with
   `case_summary + issue_type + matter_type + KG_fact_card`.
2. LLM emits a structured `QueryPlan` (schema in §4.1) — 3-5 queries each
   tagged with a `purpose` enum.
3. Each query is filtered through the leakage envelope (no extra wiring —
   `IssueRetriever` already calls through `_EvalFilteredRAGPipeline`).
4. Run all queries in parallel via `asyncio.gather`. Each retrieves
   `top_k=8` chunks (reduced per-query, since we'll fuse).
5. Concatenate result lists, dedupe by `(source_id, paragraph_id)`, fuse
   with RRF using the existing `_rrf_fusion` weighted by query
   `purpose` priors (see §2.3).
6. Apply existing repairs reranker + KG filter.
7. Trim to `top_k` (=12 in this mode, vs 5 today, because we have richer
   evidence to choose from).
8. Single prediction LLM call with the merged context.

The decomposer call is small (≈300 input tokens, ≈300 output tokens). The
prediction call sees richer context but is otherwise unchanged.

### 2.2 Decomposer prompt (sketch)

System:
```
You plan retrieval for a Housing Ombudsman repairs analysis. You emit
between 3 and 5 search queries that together would let an analyst decide
(a) whether the landlord committed maladministration, and (b) the typical
remedy band. Each query must be tagged with a purpose: "liability",
"remedy", "vulnerability", "timeline", or "adhoc".

Rules:
- Queries are short noun-phrases or natural-language fragments, not full
  questions.
- DO NOT mention the predicted outcome in any query (do not write "tenant
  wins" / "compensation awarded £" — those leak the answer).
- DO NOT include the case_id of the case being analysed.
- Cap at 5 queries. Quality beats quantity.
- ALWAYS include at least one "remedy" query asking for compensation
  amounts or order paragraphs.

Return JSON only:
{"queries": [{"purpose": "...", "text": "...", "rationale": "..."}, ...]}
```

User:
```
Issue: {issue_type}
Matter type: {matter_type}
Resident summary: {case_summary_truncated_to_400_words}
Known facts (KG): {kg_fact_card_or_"none"}
Vulnerability flag: {bool}
Awaab's Law applicability: {bool}
Severity hint: {duration_days_log_or_"unknown"}
```

The `rationale` field is for audit only — not used by retrieval. Persisted
in artifacts so we can review what the decomposer *thought* it was asking
for.

### 2.3 Purpose-weighted RRF fusion

When fusing, weight each ranked list by a per-purpose prior:

| Purpose | Weight | Reason |
|---|---:|---|
| `liability` | 1.0 | core evidence for outcome label |
| `remedy` | 1.0 | core evidence for amount band — currently missing |
| `vulnerability` | 0.7 | severity-modifier evidence |
| `timeline` | 0.6 | rule-applicability (Awaab's Law deadlines) |
| `adhoc` | 0.5 | adaptive catch-all, lowest trust |

RRF formula becomes:
```
score(chunk) = Σ_q weight(purpose_q) / (k + rank_q(chunk))
```
with `k=60` (existing constant). Implementation extends
[`_rrf_fusion` in hybrid_retriever.py:243-336](../../packages/rag_engine/retrieval/hybrid_retriever.py:243)
to accept a per-list weight dict.

### 2.4 Code surface (B)

| File | Change | LOC |
|---|---|---:|
| `packages/llm_orchestrator/pipeline/query_planner.py` | NEW — `QueryPlanner.plan(case, issue)` | ~200 |
| `packages/llm_orchestrator/prompts/packs/housing_repairs_social_v1.py` | add `query_planner_system` field | +30 |
| `packages/llm_orchestrator/pipeline/issue_retrieval.py:124-214` | new branch when mode=`decomposed`; calls `QueryPlanner.plan` then parallel-retrieves | +120 |
| `packages/rag_engine/retrieval/hybrid_retriever.py:243-336` | accept per-list weights in RRF | +20 |
| `packages/llm_orchestrator/models/prediction_v2.py` | new `RetrievalMode.DECOMPOSED` enum | +10 |
| `packages/llm_orchestrator/pipeline/prediction_engine_v2.py:89-279` | wire `retrieval_mode` arg through to retriever | +30 |
| `scripts/eval/predict_all.py` | add `--retrieval-mode` CLI flag | +20 |
| `packages/llm_orchestrator/tests/pipeline/test_query_planner.py` | NEW | ~150 |

Total ~580 LOC. No re-indexing required.

### 2.5 B tickets

- **F-AGENT-1**: `QueryPlanner` module + `query_planner_system` prompt +
  golden-prompt snapshot tests. No production wiring.
- **F-AGENT-1a**: extend RRF fusion with per-list weights; unit tests with
  synthetic ranked lists.
- **F-AGENT-1b**: wire `retrieval_mode='decomposed'` through
  `PredictionEngineV2` and `predict_all.py`. Integration test on a single
  fixture case.
- **F-AGENT-1c**: 5-case smoke vs `static_two_pass` baseline; gate on
  Amount@20% +0.05 OR Amount@£100 +0.05 with no accuracy regression. If
  smoke passes, run 50-case full eval.

---

## 3. Architecture C — iterative retrieval agent

**Goal**: when B's single-shot retrieval is insufficient, let the LLM see
the retrieved evidence and issue follow-up queries until it has enough to
predict.

### 3.1 Mechanism (state machine)

```
state = {
    "iter": 0,
    "queries_so_far": [],
    "chunks_so_far": [],   # deduped by (source_id, paragraph_id)
    "kg_facts_seen": [],
    "amounts_extracted": [],
    "tokens_used": 0,
}

loop:
    iter += 1
    if iter > MAX_ITER (=4): break with state.terminator = "max_iter"
    if tokens_used > MAX_TOKENS (=8000): break with state.terminator = "token_cap"

    # Iteration 1 IS Architecture B — same QueryPlanner call.
    if iter == 1:
        plan = query_planner.plan(case, issue)
        state.queries_so_far += plan.queries
        chunks = run_queries_parallel(plan.queries)
        state.chunks_so_far = dedupe_merge(state.chunks_so_far, chunks)
        continue

    # Subsequent iterations: LLM acts on tools.
    action = sufficiency_judge(state)   # one LLM call
    match action.tool:
        case "finalize":     break with state.terminator = "judge_ok"
        case "abstain":      break with state.terminator = "judge_abstain"
        case "retrieve":
            assert_query_safe(action.query)  # leakage guard, see §5
            chunks = run_query(action.query)
            state.queries_so_far.append(action.query)
            state.chunks_so_far = dedupe_merge(state.chunks_so_far, chunks)
        case "extract_amounts":
            amounts = extract_amounts(action.chunk_id)
            state.amounts_extracted += amounts
        case "check_kg_fact":
            fact = read_kg_fact(action.field)
            state.kg_facts_seen.append(fact)

# After loop: existing IRAC prediction call, with the agent-curated context.
prediction = issue_predictor.predict(case, issue, retrieval=state)
```

The agent's job is **only** to curate context. The final prediction is
still the same single IRAC call we already make. This keeps the calibration
story intact (one verbalized confidence, one final probability) and limits
the agent's blast radius.

### 3.2 Tool definitions

The agent sees four tools and a structured response schema. No free-form
"think out loud" — every action is a typed tool call.

```python
tools = [
    {
        "name": "retrieve",
        "description": "Search the case corpus. Filters are applied automatically; you cannot disable them.",
        "input_schema": {
            "query": str,                              # 4-15 words
            "purpose": Literal["liability","remedy","vulnerability","timeline","adhoc"],
            "section_type": Optional[Literal["facts","reasoning","orders","determination"]],
            "k": int,  # default 5, max 8
        },
    },
    {
        "name": "extract_amounts",
        "description": "Pull £-amounts from a previously retrieved chunk and return their surrounding sentences.",
        "input_schema": {"chunk_id": str},
    },
    {
        "name": "check_kg_fact",
        "description": "Read one typed KG fact about THIS case (not retrieved cases).",
        "input_schema": {
            "field": Literal[
                "vulnerability_flag","awaabs_law_applies","report_to_first_attendance_days",
                "complaint_stages_reached","prior_offer_gbp","outstanding_works_at_complaint_close"
            ],
        },
    },
    {
        "name": "finalize",
        "description": "Stop retrieval and proceed to prediction. Use only when you have enough evidence.",
        "input_schema": {"reason": str},
    },
]
```

### 3.3 Sufficiency-judge prompt

System (called every iteration ≥2):
```
You are deciding whether to gather more evidence before predicting a
Housing Ombudsman complaint outcome and remedy.

You will be shown:
- The case summary.
- The queries you have already issued.
- The chunks already retrieved (deduped, top scoring).
- Any £-amounts and KG facts already extracted.

Decide on ONE action:
- retrieve(query, purpose, ...): if a specific evidence gap remains.
- extract_amounts(chunk_id): if you see an order-paragraph chunk and have
  not yet pulled its numbers.
- check_kg_fact(field): if a typed fact would change your decision.
- finalize(reason): if you have at least one liability-relevant chunk AND
  at least one remedy-relevant chunk OR an extracted comparator amount.

Hard rules:
- DO NOT issue queries that contain the predicted outcome
  ("tenant wins","compensation £X","maladministration found").
- DO NOT issue queries that contain the case_id under analysis.
- DO NOT abstain just because evidence is mixed — abstain only if you
  cannot cite at least one supporting span for a liability finding.
- Cap: 4 total iterations. You are at iteration {iter}. Be efficient.
```

User:
```
{state_summary_rendered_as_table}
```

### 3.4 Stopping criteria (hard caps)

| Cap | Value | Rationale |
|---|---:|---|
| `MAX_ITER` | 4 | Bounds latency to 4 × judge + N × retrieve ≈ 30s |
| `MAX_TOKENS` (cumulative tool I/O) | 8000 | Lost-in-the-middle (Liu et al. TACL 2024) — prompt context ceiling |
| `MAX_CHUNKS` | 24 | Reranker quality drops past this on legal text |
| `MAX_RETRIEVES_PER_PURPOSE` | 2 | Stops endless drilling on one axis |
| Same `(query, purpose)` twice | reject | Stops degenerate loops |

Every cap hit is logged with `state.terminator` ∈ `{judge_ok,
judge_abstain, max_iter, token_cap, chunks_cap, dup_query, error}` and
persisted in the agent trace (§3.6).

### 3.5 Agent fallback when judge fails

If the judge LLM returns invalid JSON or an unknown tool name twice in a
row, the agent terminates with `state.terminator = "judge_invalid"` and
falls back to the static_two_pass result. This must NEVER abstain
silently — abstention has to be the judge's explicit decision, not an
implementation artifact, otherwise the abstention rate is uninterpretable
in eval.

### 3.6 Agent trace persistence

For every case, the agent emits a trace artifact alongside the prediction:

```jsonc
// eval/predictions/<run>/agent_traces/<case_id>.json
{
  "case_id": "housing-ombudsman-202428538",
  "iter_count": 3,
  "terminator": "judge_ok",
  "tokens_used": 6240,
  "iterations": [
    {
      "iter": 1,
      "kind": "query_plan",
      "queries": [
        {"purpose": "liability", "text": "damp mould response timelines"},
        {"purpose": "remedy", "text": "compensation orders for damp delay"}
      ],
      "chunks_added_count": 12
    },
    {
      "iter": 2,
      "kind": "tool_call",
      "tool": "extract_amounts",
      "input": {"chunk_id": "ho_202412345#para_47"},
      "output_summary": "extracted 2 amounts: 800, 1200"
    },
    {
      "iter": 3,
      "kind": "tool_call",
      "tool": "finalize",
      "input": {"reason": "sufficient liability and 3 comparator awards"}
    }
  ],
  "leakage_audit": {
    "all_queries_filter_applied": true,
    "blocked_queries": []
  }
}
```

This is the single most important artifact for thesis defensibility — it
proves what the agent did and that no leakage path was taken.

### 3.7 Code surface (C, on top of B)

| File | Change | LOC |
|---|---|---:|
| `packages/llm_orchestrator/pipeline/agentic_retriever.py` | NEW — state machine + judge loop | ~400 |
| `packages/llm_orchestrator/pipeline/agent_tools.py` | NEW — tool definitions, dispatch, leakage guards | ~250 |
| `packages/llm_orchestrator/pipeline/comparator_extractor.py` | NEW — `extract_amounts` implementation (also used by F-PROMPT-3) | ~150 |
| `packages/llm_orchestrator/prompts/packs/housing_repairs_social_v1.py` | add `sufficiency_judge_system` | +60 |
| `packages/llm_orchestrator/pipeline/issue_retrieval.py` | new branch when mode=`agentic` | +60 |
| `packages/llm_orchestrator/pipeline/prediction_engine_v2.py` | wire trace artifact | +30 |
| `scripts/eval/predict_all.py:504-536` | persist `agent_trace` in JSONL | +20 |
| `packages/llm_orchestrator/tests/pipeline/test_agentic_retriever.py` | NEW | ~300 |
| `packages/llm_orchestrator/tests/pipeline/test_agent_tools.py` | NEW | ~200 |

Total ~1470 LOC on top of B. No re-indexing.

### 3.8 C tickets

- **F-AGENT-2**: `agent_tools.py` — tool definitions, leakage guards (see
  §5.2), dispatch. Pure unit tests; no LLM.
- **F-AGENT-3**: `comparator_extractor.py` — deterministic regex+parser for
  £-amounts in order paragraphs. Reused by F-PROMPT-3 and the
  `extract_amounts` tool.
- **F-AGENT-4**: `agentic_retriever.py` — state machine, sufficiency judge,
  caps. Mock LLM tests for state transitions and cap-hits.
- **F-AGENT-5**: trace persistence + leakage audit fields in
  `predict_all.py`; round-trip serialisation tests.
- **F-AGENT-6**: 5-case smoke (same fixtures as F-AGENT-1c) vs both
  `static_two_pass` and `decomposed`; ablation table required (see §8).
- **F-AGENT-7**: full 50-case eval; gate on Amount@20% ≥ 0.30 AND no
  accuracy regression vs `decomposed`. Iff Amount@20% gain isn't ≥0.05
  over `decomposed`, deprecate C and ship only B.

---

## 4. Schemas

### 4.1 `QueryPlan` (output of B / iteration 1 of C)

```python
@dataclass
class PlannedQuery:
    purpose: Literal["liability","remedy","vulnerability","timeline","adhoc"]
    text: str  # 4-15 words; raises if longer
    rationale: str  # for trace only

@dataclass
class QueryPlan:
    queries: list[PlannedQuery]  # 3-5
    decomposer_model: str
    decomposer_tokens_in: int
    decomposer_tokens_out: int

    def validate(self) -> list[str]:
        """Return list of leakage/format violations; empty list = OK."""
```

Validation rules: see §5.1.

### 4.2 `AgentAction` (sufficiency judge output)

```python
@dataclass
class AgentAction:
    tool: Literal["retrieve","extract_amounts","check_kg_fact","finalize","abstain"]
    input: dict
    rationale: str
```

Schema-validated against the `tools` list in §3.2 before dispatch.

### 4.3 `AgentTrace` (persisted artifact)

See JSON example in §3.6. Pydantic model in
`packages/llm_orchestrator/models/agent_trace.py`.

---

## 5. Leakage invariants — non-negotiable

These are the bright lines that make agentic retrieval defensible in the
thesis. They MUST be enforced at code level, not in prompts. A prompt-only
guard against leakage is not enforceable.

### 5.1 Query content guards (B + C)

Before any planned/judge-issued query reaches the retriever, run
`assert_query_safe(query, gold_case)`:

```python
FORBIDDEN_PATTERNS = [
    r"tenant\s*win",
    r"landlord\s*win",
    r"compensation\s*£",
    r"awarded\s*£",
    r"maladministration\s*found",
    r"severe\s*maladministration\s*found",
    r"\bservice\s*failure\s*upheld\b",
]

def assert_query_safe(query: str, gold_case_id: str) -> None:
    if gold_case_id and gold_case_id.lower() in query.lower():
        raise QueryLeakageError(f"query references case under analysis")
    for pat in FORBIDDEN_PATTERNS:
        if re.search(pat, query, re.IGNORECASE):
            raise QueryLeakageError(f"query contains outcome phrase: {pat}")
```

Violations are logged in the trace and the query is dropped (not the whole
prediction — we don't want to abstain over a regex hit; we want to surface
the bad query).

### 5.2 Retrieval envelope inheritance (B + C)

The `IssueRetriever` and any tool dispatcher MUST call through the
`_EvalFilteredRAGPipeline` instance constructed in
[predict_all.py:196-213](../../scripts/eval/predict_all.py:196). The agent
cannot construct its own `RAGPipeline`; it can only call methods on the
filtered instance. This is enforced by:

- `agent_tools.py` does not import `RAGPipeline` directly.
- It receives the `rag` object via dependency injection from the engine.
- A unit test (`test_agent_tools_envelope.py`) constructs an agent with
  a `RAGPipeline` whose `retrieve()` raises if `kwargs["filters"]` is None;
  the test asserts every `retrieve` tool call propagates the envelope.

### 5.3 Forbidden tool surfaces (C)

The agent MUST NOT have access to:

- The gold row's `ground_truth_outcome`, `total_awarded_gbp`, `decision_date`,
  `key_reasoning_quotes`, `statutory_basis`, `cited_authorities`,
  `disputed_amount_gbp`, `claimed_amounts`. The case file passed to the
  agent is the *post-stripping* `CaseFile` from
  [`gold_case_to_case_file`](../../packages/eval/case_file_adapter.py:97).
- A `read_gold_field(field_name)` tool (don't add one, even for debugging).
- The retrieved chunks of the target source itself — already excluded by
  `excluded_source_ids` in the envelope.
- Network or file-system tools.

The tool list in §3.2 is closed: adding a tool requires an explicit
review against this section.

### 5.4 Trace audit gate

A new eval step `audit_agent_traces` runs after `run_full_eval.py` and
asserts, per case:

- Every `retrieve` action has `leakage_audit.all_queries_filter_applied = true`.
- No action's `input` JSON contains the gold case_id.
- No action's `input` JSON matches `FORBIDDEN_PATTERNS`.
- `terminator != "error"` for ≥95% of cases (otherwise eval is bad).
- Median `iter_count ≤ 3`, p99 `iter_count ≤ 4`.

If any audit fails, `summary.json` carries `is_clean=false` and the eval
run is not a valid baseline. Same convention as the existing leakage
audit.

---

## 6. Cost & latency budgets

Per-case wall-clock and dollar cost on a 50-case eval, modelled on
GPT-4o-mini ($0.15/1M in, $0.60/1M out) for decomposer/judge and
Sonnet 4.6 ($3/1M in, $15/1M out) for the prediction call:

| Mode | Decomposer calls | Judge calls | Predict calls | Avg in tokens | Avg out tokens | Wall (s) | Cost ($/case) |
|---|---:|---:|---:|---:|---:|---:|---:|
| `static_two_pass` | 0 | 0 | 1 | 8k | 1.5k | ~10 | $0.046 |
| `decomposed` (B) | 1 | 0 | 1 | 9k | 1.6k | ~13 | $0.047 |
| `agentic` (C, p50) | 1 | 1.5 | 1 | 12k | 2.5k | ~25 | $0.055 |
| `agentic` (C, p99) | 1 | 3 | 1 | 22k | 4k | ~50 | $0.094 |

Numbers are rough. Two budget rules go in CI:

- **Per-case cost cap**: $0.15 (kills runaway iteration loops).
- **Per-case wall cap**: 90s (kills hung judges).

A 50-case eval at C-p50 is ~$2.75 and ~21 minutes. Acceptable.

---

## 7. Calibration & abstention coupling

### 7.1 Why this matters

Today's calibration plan (F-CAL-1 in master plan) fits temperature scaling
on `verbalized_confidence_pct` from the single prediction call. With B and
C, the prediction call is *still single*, so the calibrator stack is
unchanged. **This is a deliberate design choice** — we do not let the
agent's intermediate confidences leak into the final probability.

### 7.2 Abstention sources

There are now three abstention paths. Each produces the same
`outcome=uncertain` for backward compatibility but logs a distinct reason:

| Path | When | abstention_reason field |
|---|---|---|
| Predictor abstains | model emits `outcome=uncertain` despite having evidence | `predictor_uncertain` |
| Citation verifier strips all cites | no verified support for any non-uncertain prediction | `citation_strip` |
| Agent judge picks `abstain` | judge decides no liability span exists after retrieval | `judge_abstain` |
| Agent terminator = `max_iter`/`token_cap` | hit a hard cap with insufficient evidence | `agent_capped` |

The eval reports abstention rate broken down by reason. This was
explicitly missing in the current artifacts ([taxonomy §E](../eval/housing-ombudsman-failure-taxonomy-2026-05-05.md))
and is required to interpret B/C performance.

### 7.3 Conformal abstention plays nicely

F-EVAL-3 (conformal classification sets) operates on the final prediction
call's confidence, so it composes with B and C without changes. It will,
however, see different confidence distributions in each mode — that's fine
and expected.

---

## 8. Eval modes & ablation matrix

The thesis-grade ablation table for the final report:

| # | Mode | Retrieval | KG card | Calibrator | Bands | Cite-or-abstain | Notes |
|---|---|---|---|---|---|---|---|
| 0 | `always_tenant` | — | — | — | — | — | baseline (currently 0.98 acc) |
| 1 | `llm_only_no_retrieval` | none | none | none | — | — | renamed from `llm_only` |
| 2 | `kg_only_no_retrieval` | none | typed | none | — | — | renamed from `kg_only`, with F-KG-1 |
| 3 | `static_two_pass_rag` | F-RET-1 | none | F-CAL-1 | F-AMT-1 | yes | new RAG baseline |
| 4 | `static_two_pass_hybrid` | F-RET-1 | typed | F-CAL-1 | F-AMT-1 | yes | new hybrid baseline |
| 5 | `decomposed_hybrid` (**B**) | F-AGENT-1 | typed | F-CAL-1 | F-AMT-1 | yes | one decomposer call |
| 6 | `agentic_hybrid` (**C**) | F-AGENT-2..5 | typed | F-CAL-1 | F-AMT-1 | yes | iteration loop |

We need rows 3-6 to credibly claim "B improves over static" or "C improves
over B". Rows 1 and 2 stay in for completeness but their honest framing
(see [master plan §8](hybrid-rag-improvement-plan-2026-05-05.md)) is "no
retrieval ablation, abstains universally".

Each row reports the full metric stack from F-EVAL-1: accuracy, macro-F1,
balanced acc, MCC, Brier, ECE, AURC, abstention rate by reason,
Amount@20%, Amount@£100, MAE, bias, per-band MAE.

The thesis comparison hinges on rows 4 vs 5 (deterministic vs B) and
rows 5 vs 6 (B vs C). Promote C to default ONLY if Δaccuracy ≥ 0.03 OR
Δmacro-F1 ≥ 0.05 OR Δamount@20% ≥ 0.05 over row 5.

---

## 9. Test plan

### 9.1 Unit tests

| Module | Test name | What it asserts |
|---|---|---|
| `query_planner` | `test_emits_at_least_one_remedy_query` | every plan has ≥1 `purpose='remedy'` |
| `query_planner` | `test_rejects_outcome_phrases` | `assert_query_safe` rejects all `FORBIDDEN_PATTERNS` |
| `query_planner` | `test_rejects_self_reference` | query containing gold case_id is rejected |
| `query_planner` | `test_caps_query_count_at_5` | input that elicits 7 queries gets truncated to 5 |
| `agent_tools` | `test_retrieve_propagates_envelope` | mocked RAG raises iff filters missing — agent must propagate |
| `agent_tools` | `test_extract_amounts_no_lookup_outside_chunks_so_far` | extraction tool refuses unknown chunk_id |
| `agent_tools` | `test_check_kg_fact_only_typed_fields` | tool rejects `field='ground_truth_outcome'` etc. |
| `agentic_retriever` | `test_max_iter_cap` | judge always says retrieve → terminator=`max_iter` after 4 iters |
| `agentic_retriever` | `test_dup_query_rejected` | same `(query, purpose)` twice → terminator=`dup_query` |
| `agentic_retriever` | `test_judge_invalid_falls_back` | malformed judge JSON twice → fallback to static_two_pass |
| `agentic_retriever` | `test_terminator_logged` | every termination path writes a `terminator` field |
| `comparator_extractor` | `test_extracts_pound_amounts_with_para_id` | regex-finds £700, £1,250 with paragraph context |
| `rrf_fusion` | `test_per_list_weights_change_order` | weighted RRF shifts ranks vs unweighted |

### 9.2 Smoke fixtures (5 cases)

Reuse the master plan §7 fixtures:
- `housing-ombudsman-202428538` (£3818 amount-band miss)
- `housing-ombudsman-202413497` (hybrid abstain, rag right)
- `housing-ombudsman-202413845` (only confident-wrong; possible gold issue)
- `housing-ombudsman-202509792` (£0 prediction, gold £1500)
- `housing-ombudsman-202306436` (lone landlord case)

For each, snapshot-test the agent trace shape (not the content, since LLM
outputs vary) and assert no leakage audit failure.

### 9.3 Promotion gates

| Gate | Threshold |
|---|---|
| All unit tests pass | required |
| Trace audit passes on all 5 smoke cases | required |
| Mode B: 5-case smoke shows ≥+0.05 on Amount@20% OR Amount@£100 vs `static_two_pass`, no accuracy regression | promote to 50-case |
| Mode B: 50-case full eval | replaces `static_two_pass` as default if Δamount@£100 ≥ 0.05 |
| Mode C: 5-case smoke shows ≥+0.05 on Amount@20% OR macro-F1 vs `decomposed` | promote to 50-case |
| Mode C: 50-case full eval | promote to default ONLY if §8 thresholds met |

---

## 10. Implementation roadmap

### Phase 1 — prerequisites (already in master plan)

1. F-EVAL-1 (macro-F1, balanced acc, MCC, abstention-adjusted) — *needed
   to honestly compare modes*
2. F-EVAL-2 (persist verifier output) — *needed to audit citations*
3. F-MODE-1 (rename kg_only/llm_only honestly) — *removes a confound from
   the ablation table*
4. F-CAL-1 (temperature scaling) — *applies to all modes uniformly*
5. F-AMT-1 (band schema) — *needed before the agent can target remedy bands*

### Phase 2 — Architecture B

6. F-AGENT-1 — `QueryPlanner` module + tests (no wiring)
7. F-AGENT-1a — RRF per-list weights
8. F-AGENT-1b — wire `retrieval_mode='decomposed'` end-to-end
9. F-AGENT-1c — 5-case smoke → 50-case eval

### Phase 3 — Architecture C (only if B is shipped and stable)

10. F-AGENT-2 — agent tool framework + leakage guards (unit-only)
11. F-AGENT-3 — `comparator_extractor`
12. F-AGENT-4 — `agentic_retriever` state machine + judge prompt
13. F-AGENT-5 — trace persistence + audit step
14. F-AGENT-6 — 5-case smoke vs B
15. F-AGENT-7 — 50-case eval; promote-or-deprecate decision

### Phase 4 — only after Phase 3 lands

16. F-RET-4 (Summary-Augmented Chunking) — re-indexing work; orthogonal
    to B/C
17. F-AMT-2 (within-band CQR) — uses agent's extracted comparator amounts
18. F-VERIFY-2 (Chain-of-Verification) — runs *after* agent retrieval but
    *before* prediction; ablate carefully

Total estimated effort: B ≈ 3-5 dev-days; C ≈ 8-12 dev-days; both gated on
Phase 1 (≈ 5-7 dev-days). Realistic: 4-6 weeks elapsed.

---

## 11. What still can't be claimed

Even with B and C shipped:

1. **You still cannot claim "agentic > deterministic" on the current
   50-case slice.** Until F-DATA-1 lands you are still grading models
   against `always_tenant=0.98`. The 50-case slice cannot adjudicate
   ablation claims.

2. **You cannot claim B or C reduces hallucination without trace audit
   results.** The leakage audit (§5.4) is the *only* defensible artifact;
   prompt-level guards do not count.

3. **You cannot claim the agent "decides what to retrieve" if the trace
   shows median iter_count = 1.** If the judge always picks `finalize` on
   iteration 2, C is operationally identical to B and should be deprecated.

4. **You cannot quote the agent's intermediate confidences.** The only
   calibrated probability is the final prediction call's
   verbalized_confidence after F-CAL-1.

5. **You cannot compare against L-MARS / Self-RAG headline numbers.**
   Different corpus, different task. Cite their methodology, not their
   numbers, when motivating B/C.

6. **You should not market the architecture as "novel agentic legal
   reasoning"** — the agent only curates retrieval context; the
   reasoning is still a single IRAC call. Frame it accurately:
   "agent-curated retrieval over a deterministic IRAC predictor, with
   conformal abstention and band-level remedy prediction."

---

## 12. Appendix — open questions to resolve during implementation

- **Does the decomposer benefit from seeing past retrieved chunks?**
  Today B is single-shot before any retrieval. A 1.5-shot variant
  ("decompose, retrieve, decompose-again-with-gaps") could close the gap
  to C at lower cost. Pilot if B-vs-C delta is small.
- **Is purpose-weighted RRF stable on small corpora?** If the Ombudsman
  corpus has few `orders`-type chunks for niche issues, weighting up
  `remedy=1.0` could starve other purposes. Monitor per-purpose recall.
- **Should `extract_amounts` be deterministic only, or LLM-augmented?**
  Determinism is safer (no leakage, reproducible). Start there;
  reconsider only if regex misses too many real award lines.
- **Cache warming**: the decomposer prompt is highly cacheable
  (system+rules ≈800 tokens, near-stable). Enable Anthropic prompt
  caching if we route through Sonnet. Should drop B's marginal cost by
  ≥80%.
- **Multi-issue cases**: today repairs has one issue per case. If we
  generalise to deposit/employment, the agent must run per-issue and
  fuse — this is straightforward but doubles the call count for
  multi-issue matters.

---

**Companion docs**:
- Master plan: [`hybrid-rag-improvement-plan-2026-05-05.md`](hybrid-rag-improvement-plan-2026-05-05.md)
- Index: [`hybrid-rag-improvement-INDEX-2026-05-05.md`](hybrid-rag-improvement-INDEX-2026-05-05.md)
- Code audit: [`hybrid-rag-current-pipeline-audit-2026-05-05.md`](hybrid-rag-current-pipeline-audit-2026-05-05.md)
- Failure taxonomy: [`../eval/housing-ombudsman-failure-taxonomy-2026-05-05.md`](../eval/housing-ombudsman-failure-taxonomy-2026-05-05.md)
- Retrieval research: [`hybrid-rag-improvement-research-retrieval-2026-05-05.md`](hybrid-rag-improvement-research-retrieval-2026-05-05.md)
- Prompting/calibration research: [`hybrid-rag-improvement-research-prompting-calibration-2026-05-05.md`](hybrid-rag-improvement-research-prompting-calibration-2026-05-05.md)
