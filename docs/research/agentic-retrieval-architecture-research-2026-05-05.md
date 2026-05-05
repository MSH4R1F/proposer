# Agentic Retrieval Architecture — Primary-Source Research (2026-05-05)

**Scope**: How to build the iterative retrieval agent in
[`hybrid-rag-agentic-retrieval-plan-2026-05-05.md`](hybrid-rag-agentic-retrieval-plan-2026-05-05.md)
§3 (Architecture C). Bias toward maximally-LLM-driven design (the LLM
picks queries, judges sufficiency, decides termination) with the minimum
defensible deterministic envelope around it.

**Out of scope**: hybrid retrieval recall improvements, calibration,
amount-band schema (covered in companion research files).

**Companion research already done**:
[`hybrid-rag-improvement-research-retrieval-2026-05-05.md`](hybrid-rag-improvement-research-retrieval-2026-05-05.md)
covers Magesh et al. on hallucinations in legal RAG, Rasiah et al. (SAC),
Anthropic Contextual Retrieval, and GraphRAG critiques — those are not
re-derived here.

---

## 1. Executive summary

After surveying L-MARS, Self-RAG, CRAG, FLARE, IRCoT, ReAct, Reflexion,
EviMem, the OpenTelemetry GenAI conventions and the Langfuse / Phoenix /
Weave landscape, my five top architectural recommendations for our
4-tool, 4-iteration agent:

1. **Adopt L-MARS's Judge-loop pattern as the spine, not Self-RAG.**
   Self-RAG's reflection-token mechanism requires a fine-tuned model
   ([Asai 2024, §2][1]); a prompt-engineered judge that returns
   `{sufficient: bool, next_query?: str}` is the same control signal at
   a fraction of the engineering cost, and is exactly what L-MARS ships
   ([L-MARS GitHub][3]). Use it.
2. **Hand-roll the state machine in raw Anthropic SDK + Pydantic.** A
   four-tool, four-iteration loop is too small for LangGraph's
   abstraction tax and too imperative for DSPy's compile-and-optimise
   model. The case for a framework arrives at ≥3 branching nodes or
   parallel agents — we have neither.
3. **Sufficiency = single LLM call with structured `confidence` + tool
   choice** (per EviMem's Spearman ρ=0.93 between confidence and oracle
   sufficiency, [EviMem 2026][9]). Confidence threshold defaults: 0.70
   for liability tier, 0.85 for amount-band tier.
4. **Termination policy in priority order**: (a) judge picks `finalize`
   above τ=0.70, (b) duplicate `(query, purpose)` rejected, (c) hard
   cap MAX_ITER=4 / MAX_TOKENS=8k. ReAct used 7 steps for HotpotQA and
   converged ([Yao 2023][6]); legal Ombudsman cases are simpler — 4 is
   enough.
5. **Traces: Langfuse self-hosted + OpenTelemetry GenAI conventions.**
   It is OSS, schema-stable, free at our volume, and Langfuse traces
   align with the `gen_ai.*` semantic conventions
   ([OTel SemConv 2026][13]) which Harvey publicly adopts via the
   OpenAI Agent SDK ([Harvey 2026][16]). Phoenix is a credible second
   choice if we want stronger built-in eval primitives.

**One-line architecture stack** (claimed up front so the rest of this
doc justifies it): *raw Anthropic SDK + Pydantic state machine + LLM-as-judge
sufficiency with `confidence_score` + Langfuse OTel traces + regex-first
amount extractor with LLM fallback.*

---

## 2. Findings by topic

### 2.1 L-MARS deep dive

**Claim**: L-MARS is the closest production precedent to what we need
and its Judge agent is straightforward to port.

**Architecture (4 agents)** — confirmed from `lmars/agents.py` and
`lmars/workflow.py` on GitHub ([L-MARS code][3]):

| Agent | Job | Output |
|---|---|---|
| Query Agent | parse the user question into structured search intents | sub-queries |
| Search Agent | retrieve evidence from enabled sources (web / corpus) | result list |
| Judge Agent | evaluate whether evidence is sufficient | `JudgeDecision{sufficient, reason, next_query?}` |
| Summary Agent | synthesise cited answer | final answer |

**Judge stopping criterion**: structured JSON
`{"sufficient": bool, "reason": str, "next_query": str|None}` returned
by the Judge Agent. The system prompt instructs the model that
sufficiency means at least one retrieved result contains
"specific legal rules, statutes, case holdings, or doctrinal exceptions"
([L-MARS code][3]). On `sufficient=true` the loop breaks; on `false` the
next query is either the judge's `next_query` or a fallback enrichment.
There is **no confidence score** in upstream L-MARS — it is binary. We
should add one (see §2.6).

**State sharing**: a flat dict that accumulates across turns —
`current_query`, `all_results` (deduped by URL/title via `seen_keys`),
`search_history`, `judge_log`. No graph framework; it is a `for turn in
range(self.config.max_turns)` loop in `workflow.py`.

**Termination implementation note** worth copying: the Judge is
explicitly **not run on the final iteration** — the loop force-breaks
into synthesis. This guarantees a deterministic stop even if the judge
is broken. We should mirror this with our `MAX_ITER` cap.

**Citation grounding**: per-claim citations in the Summary Agent
output, traced to `seen_keys` URLs. Not novel — what is novel is that
citations are emitted *inside* the loop's accumulated state, not
synthesised after the fact.

**Headline numerics** (LegalSearchQA, 50-question benchmark,
post-training-cutoff legal questions): zero-shot 58.0% → L-MARS 96.0%,
i.e. +38.0 pp; CoT prompting 30.0% (worse than zero-shot).
Tax / Corporate sub-domain: +61.5 pp ([L-MARS abstract][2];
[arXiv 2509.00761][14]). [Confidence: High]

**Limitations / cautions**:
- LegalSearchQA is 50 questions and skewed toward post-cutoff facts
  where retrieval is uniquely valuable. Our task (predicting the
  Ombudsman's decision) is different — recall is necessary but not
  sufficient. Cite the methodology, not the +38pp number, when
  motivating C.
- L-MARS's Search Agent calls live web search; ours retrieves from a
  closed Ombudsman corpus with a leakage filter. The leakage envelope
  (§5.2 of the plan) is the most important divergence — L-MARS does
  not need it.
- No reported per-iteration latency or token budget.

### 2.2 Self-RAG: do we need to retrain?

**Claim**: Self-RAG's reflection-token mechanism cannot be replicated
without retraining; the prompt-engineered analogue is L-MARS-style
judge prompting, with the same control signal but no token-level
gating.

Self-RAG ([Asai et al. ICLR 2024][1]) trains a single LM to emit four
reflection tokens during generation: `Retrieve` (do I need a
passage?), `ISREL` (is the passage relevant?), `ISSUP` (is the
generated segment supported?), `ISUSE` (1-5 utility score). The
training objective specifically supervises these tokens; you cannot
recover the same calibration from a frontier model with prompts alone
because the tokens carry weight under softmax sampling in the
fine-tuned distribution, not the base distribution.

The closest prompt-engineered cousins:

- **CRAG** ([Yan et al. 2024][4]): trains a 0.77B T5 retrieval
  evaluator that returns `{Correct, Incorrect, Ambiguous}` and
  triggers different actions per state. Not a frontier-model approach
  — they explicitly compare against Self-RAG's 7B critic model and
  argue for the smaller fine-tuned evaluator.
- **FLARE** ([Jiang et al. EMNLP 2023][5]): triggers retrieval when
  any token's predicted probability falls below θ ∈ [0,1]. Reports
  retrieval is triggered for ~30-60% of sentences. Requires logprobs
  access — fine on Anthropic API for input tokens but not for
  generated tokens at the granularity FLARE expects.
- **IRCoT** ([Trivedi et al. ACL 2023][7]): interleaves retrieval and
  reasoning step-by-step; terminates when the chain-of-thought
  contains "answer is" or hits a step cap (default 5).

**Verdict**: A judge-call returning `{sufficient: bool,
confidence_score: float, next_query?: str}` is the operationally
useful subset of Self-RAG that we *can* run with Sonnet/Opus.
Calibration of `confidence_score` is something we do post-hoc with
temperature scaling (F-CAL-1 in our master plan), not at generation
time.

[Confidence: High] — primary sources unambiguous.

### 2.3 IRCoT, FLARE, Active RAG, ReAct, Reflexion summary

For each: stopping criterion / cycle detection / retraining /
reported gain over single-shot.

| Method | Stop signal | Cycle detection | Retrain? | Gain over single-shot |
|---|---|---|---|---|
| IRCoT | "answer is" in CoT, else cap (default 5 steps) ([Trivedi 2023][7]) | none | no | retrieval +21 pts; QA +15 pts on HotpotQA/2WikiMultihopQA/MuSiQue/IIRC ([Trivedi 2023][7]) |
| FLARE | every token prob > θ ⇒ stop; sentence-level loop ([Jiang 2023][5]) | implicit (regenerated sentences) | no | small but consistent across 4 datasets; key finding: retrieval triggered 30-60% of sentences |
| ReAct | `Finish` action OR step cap (7 HotpotQA, 5 FEVER) ([Yao 2023][6]) | none in paper | no | best when combined with CoT-SC; alone weaker than CoT |
| Reflexion | task success OR trial cap; **3 identical action+obs cycles ⇒ trigger reflection**; **30 actions ⇒ stop** ([Shinn 2023][8]) | yes — heuristic | no (verbal RL) | up to 22% on AlfWorld over ReAct; legal applicability unclear |
| CRAG | retrieval evaluator confidence sets `{Correct, Incorrect, Ambiguous}` action ([Yan 2024][4]) | n/a | yes (T5-large) | +5-7 pts on PopQA, Biography, PubHealth |
| Self-RAG | `Retrieve` token at decode time ([Asai 2024][1]) | n/a | yes (Llama-2 7B/13B) | varies by benchmark; key is on-demand retrieval |
| EviMem | confidence ≥ θ AND tier ∈ {EXACT, INFERRABLE}, else cap k=3 ([EviMem 2026][9]) | yes — entity tracking | no | +23 pp on temporal QA, 4.5× faster than baseline |

**Most relevant to us**: L-MARS (legal, recent, OSS), Reflexion (cycle
detection heuristics we should copy), EviMem (confidence-tiered
sufficiency we should copy).

[Confidence: High] for all numerical claims — each is from the primary
paper or its public code.

### 2.4 Recent legal agent papers

Beyond L-MARS:

- **ChatLaw** ([Cui et al. 2024, arXiv 2306.16092][10]) — four agents:
  initial info gathering, deep research, legal advice, final report.
  KG-enhanced MoE. Reports +7.73% accuracy over GPT-4 on Lawbench and
  +11 points on Chinese Unified Legal Qualification Exam. **No
  ablation of single-call vs agentic** in the public paper. Caveat:
  Chinese law domain.
- **GLIER** (arXiv 2604.23779) — generative legal inference + evidence
  ranking for case retrieval; ranking-focused, not a full agent.
- **LLM Agents in Law: Taxonomy** ([arXiv 2601.06216][11]) — survey
  paper, useful as a reference index but no novel architecture.
- **Towards Trustworthy Legal AI through LLM Agents and Formal
  Reasoning** ([arXiv 2511.21033][12]) — adds Lean / Z3-style formal
  verification atop LLM agents; relevant for tenancy but heavy
  infrastructure for our scope.
- **Magesh et al. on legal RAG hallucinations** ([Stanford DHO 2025
  preprint][15]) — bare RAG hallucinates 17-33% on legal tools; argues
  for span-level verification. We already cite this in the retrieval
  research; the agentic relevance is that *agentic* retrieval doesn't
  by itself reduce hallucination — verification does.

**The single most useful single-call vs agentic ablation in the
literature is L-MARS's Simple Mode vs Multi-Turn Mode** ([L-MARS][14]):
single-turn retrieval-then-answer vs the four-agent loop. They report
Multi-Turn produces "more thorough and contextually grounded answers"
but the 38pp number is the multi-turn vs *zero-shot* gap; the Simple
Mode delta is smaller and not headline-quoted in the abstract.

[Confidence: Moderate] — we need to read the L-MARS paper body to nail
the Simple Mode number; the PDF was unparseable on a first pass.

### 2.5 Production agent observability

**Convergence**: by April 2026 the production conversation is six
platforms: LangSmith, Langfuse, Arize Phoenix, Helicone, Datadog LLM
Observability, Honeycomb LLM Observability ([Digital Applied 2026][17]).
For a single thesis project that needs OSS + self-host + free:

| Tool | Open source | Self-host | OTel GenAI | Eval primitives | Verdict |
|---|---|---|---|---|---|
| Langfuse | yes (MIT) | yes (Postgres + ClickHouse) | yes | LLM-as-judge built in | **pick this** |
| Arize Phoenix | yes (ELv2) | yes | yes | best-in-class eval / drift | strong second choice |
| Weave (W&B) | partly | yes via W&B | yes | tied to W&B | only if already on W&B |
| LangSmith | no | hosted only | yes | yes | tied to LangChain |
| OpenLLMetry / Helicone | yes | yes | yes | weaker eval | proxy-style; lighter than Langfuse |

**OpenTelemetry GenAI semantic conventions (March 2026, experimental)**
([OTel SemConv][13]):
- Required: `gen_ai.operation.name`, `gen_ai.provider.name`.
- Agent-specific (conditionally required): `gen_ai.agent.name`,
  `gen_ai.agent.id`, `gen_ai.agent.description`, `gen_ai.agent.version`.
- Per-span: `gen_ai.tool.definitions`, `gen_ai.input.messages`,
  `gen_ai.output.messages`, `gen_ai.usage.input_tokens`,
  `gen_ai.usage.output_tokens`, `gen_ai.response.finish_reasons`.
- Conversation: `gen_ai.conversation.id` (we map to `case_id`).

**Production-shop disclosures**:
- Harvey publicly states "OpenAI Agent SDK's OpenTelemetry traces"
  power their offline evals in LangSmith ([Harvey blog 2026][16]); they
  describe a five-step loop with a "Completeness Check" before
  synthesis but do not name an LLM-judge component.
- Casetext / Thomson Reuters CoCounsel: no public agent-trace schema.
- Hebbia: no public agent-trace schema.

**Trace-fields the literature converges on**:
`{trace_id, parent_id, span_id, operation_name, agent_name, tool_name,
input, output, latency_ms, input_tokens, output_tokens, model,
status, error}` — this maps 1:1 to OTel `gen_ai.*` and to Langfuse's
internal model. Use it as our `agent_trace.json` schema (see §3.4).

[Confidence: High] for OTel; [Moderate] for Harvey internals.

### 2.6 Termination & cycle detection — what production teams actually do

The literature's converged pattern:

1. **Sufficiency LLM-as-judge with structured `confidence_score`** —
   EviMem reports Spearman ρ=0.93 between LLM-emitted confidence and
   oracle sufficiency on long-context conversational memory; threshold
   commitments at EXACT precision 97.9%, INFERRABLE precision 91.3%
   ([EviMem 2026][9]). This is the strongest evidence we have that
   confidence-tiered sufficiency works.
2. **Cycle/duplicate detection** — Reflexion's heuristic
   ("3 identical action+obs cycles ⇒ trigger reflection",
   "30 actions ⇒ stop") is 3 years old and still the standard
   ([Shinn 2023][8]). Our equivalent: reject duplicate
   `(query, purpose)` and dedupe chunks by `(source_id, paragraph_id)`.
3. **Hard caps as last-resort fallback** — every paper has them;
   ReAct=7, IRCoT=5, EviMem=3, L-MARS user-configurable. We pick 4
   because: (a) Ombudsman cases have at most two evidence axes
   (liability + remedy), (b) median iter_count ≥ 3 is a hard
   thesis-promotion gate (§5.4 of the plan).
4. **No one uses chunk-overlap or "diminishing returns" detection in
   the recent literature** — it's an old trick from
   information-retrieval research that frontier-LLM papers have
   abandoned. The judge is more capable than a Jaccard threshold. We
   do *not* implement chunk-overlap stopping.

[Confidence: High] for ranking; [Moderate] for the no-Jaccard claim
(absence of evidence).

### 2.7 Maximally-LLM-driven design — per-tool recommendations

The user's principle: minimise hand-rolled heuristics. For each seam
in the planned architecture (§3.2 of the plan):

| Seam | Today's plan | LLM-driven option | Recommendation |
|---|---|---|---|
| `extract_amounts` | regex+parser | LLM JSON parse of chunk | **Hybrid: regex first, LLM fallback when regex returns 0 amounts on an `orders/determination`-typed chunk.** Regex is reproducible and audit-friendly for the 90% case (`£1,250`); LLM is required for "twelve hundred and fifty pounds" (vanishingly rare in Ombudsman text — it is administrative, not narrative). Determinism wins by default; LLM is the safety net. |
| `assert_query_safe` | regex blocklist | LLM critic | **Keep regex.** The forbidden-pattern list (§5.1 of the plan) is short, fully enumerable, and a single regex hit blocks the query — there is no judgement. An LLM critic adds a second LLM call and a non-deterministic gate to a leakage rule that *must be deterministic for the trace audit to be valid* (§5.4 of the plan). |
| Sufficiency judge output | structured Action enum | natural-language reasoning + tool call | **Structured Pydantic Action with `confidence_score: float ∈ [0,1]` and `rationale: str`.** EviMem's ρ=0.93 ([EviMem 2026][9]) plus the L-MARS Judge schema ([L-MARS code][3]) plus our temperature-scaling calibrator (F-CAL-1) all want a numeric handle. Free-form text is harder to gate on, harder to log, and harder to defend in a thesis. |
| RRF fusion weights | per-purpose hardcoded | LLM-suggested per case | **Keep hardcoded.** RRF weights are an inductive bias informed by domain (remedy=1.0 because we are missing remedy chunks today — see master plan §1.6). An LLM-emitted weight per case is unaudtiable, unstable, and the marginal recall gain over a hand-tuned table is probably small. **Open question**: revisit if per-purpose recall analysis shows the table is wrong. |
| Decomposer prompt | one-shot QueryPlan | iterative ("decompose, retrieve, decompose-with-gaps") | Already deferred in plan §12; revisit if B-vs-C delta is small. |

**Headline principle**: LLM-drive the *judgement* (sufficiency, query
choice, rationale) and keep the *invariants* (leakage guard, dedup,
caps) deterministic. This is the same split L-MARS, EviMem and Harvey
all converge on.

[Confidence: High] — the recommendation rests on a clean
deterministic↔LLM-driven taxonomy that the plan already implies.

### 2.8 Framework choice — DSPy vs LangGraph vs hand-rolled

For a 4-tool, 4-iteration agent with one decision point per
iteration:

- **LangGraph** is "a state machine for AI agents" with nodes/edges,
  built-in checkpointing, and human-in-the-loop hooks
  ([LangWatch 2025][18]). Strength: explicit graph topology,
  visualisable. Cost: framework overhead is real, learning-curve is
  non-trivial. **Justified at ≥3 nodes / parallel agents / branching
  on tool output.** We have a single linear loop.
- **DSPy** is declarative prompt optimisation — you write what you
  want, the compiler tunes prompts. Strength: prompt optimisation
  becomes ML. Cost: DSPy is "stateless by default; context must be
  manually managed" ([Medium 2025][18b]); the compile step is itself
  a workflow. **Justified when prompts will be tuned over many
  examples.** Our 50-case eval is borderline; once we hit ≥200 cases
  it is worth revisiting.
- **Hand-rolled (raw Anthropic SDK + Pydantic)** — a `while iter <
  MAX_ITER` loop, four `@tool` decorated functions, one Pydantic
  `AgentAction` model, OTel spans on each call. ~300 LOC.

**Recommendation**: hand-rolled. The agent is too small for the
framework tax. Adopt LangGraph if/when we add a second decision
point (e.g. multi-issue routing, explicit pre-prediction
verification). Adopt DSPy only after we have an offline evaluation
loop big enough to compile against (post-thesis).

[Confidence: Moderate] — opinionated, but defensible.

---

## 3. Synthesis: recommended architecture for our use case

### 3.1 State machine pseudocode (~30 lines)

```python
class AgentState(BaseModel):
    case_id: str
    issue_type: str
    iter: int = 0
    queries_so_far: list[PlannedQuery] = []
    chunks_so_far: list[Chunk] = []           # deduped on insert
    kg_facts_seen: list[KGFact] = []
    amounts_extracted: list[Amount] = []
    tokens_used: int = 0
    terminator: Optional[str] = None
    judge_log: list[AgentAction] = []         # one per iter ≥ 2

def run_agent(case: CaseFile, issue: Issue, rag, llm) -> AgentState:
    s = AgentState(case_id=case.id, issue_type=issue.type)
    plan = query_planner.plan(case, issue, llm)             # iter 1 = Architecture B
    s.iter = 1
    s.queries_so_far += plan.queries
    s.chunks_so_far = dedupe_merge([], rag.run_parallel(plan.queries))

    while s.iter < MAX_ITER:                                # MAX_ITER = 4
        s.iter += 1
        if s.tokens_used > MAX_TOKENS: return _stop(s, "token_cap")
        if len(s.chunks_so_far) > MAX_CHUNKS: return _stop(s, "chunks_cap")

        action = sufficiency_judge(s, llm)                  # one LLM call
        s.judge_log.append(action)

        if action.tool == "finalize" and action.confidence_score >= 0.70:
            return _stop(s, "judge_ok")
        if action.tool == "abstain":
            return _stop(s, "judge_abstain")

        if (action.tool, action.input.get("query")) in _seen(s):
            return _stop(s, "dup_query")                    # cycle guard

        try:
            s = dispatch_tool(action, s, rag)               # retrieve / extract / kg
        except QueryLeakageError:
            continue                                        # drop bad query, keep going

    return _stop(s, "max_iter")
```

Notes:
- `dedupe_merge` enforces the dedup invariant on `(source_id, paragraph_id)`.
- `dispatch_tool` runs the tool and updates token/chunk counters.
- `_stop(s, terminator)` writes `s.terminator` and returns.
- `MAX_TOKENS=8000`, `MAX_CHUNKS=24` — copied from plan §3.4.
- Confidence threshold τ=0.70 for `finalize`; below that, the judge's
  `finalize` is treated as a coin-flip and we keep going (subject to
  caps).

### 3.2 Sufficiency-judge prompt skeleton (~40 lines)

System (cached via Anthropic prompt caching — stable per matter type):
```
You are deciding whether enough evidence has been gathered to predict
a Housing Ombudsman repairs complaint outcome and remedy.

You return ONE structured action via tool call. Available actions:
- retrieve(query, purpose): if a specific evidence gap remains.
- extract_amounts(chunk_id): if you see an order-paragraph chunk and
  have not yet pulled its £-amounts.
- check_kg_fact(field): if a typed fact about THIS case would change
  your decision (e.g. vulnerability_flag, awaabs_law_applies).
- finalize(reason, confidence_score): if you have at least one
  liability-relevant chunk AND at least one remedy-relevant chunk OR
  an extracted comparator amount.
- abstain(reason): only if no liability-supporting span exists after
  retrieval. Abstaining is recorded as 'uncertain'; do not abstain
  because evidence is mixed.

Output schema (validated):
{
  "tool": "<one of the above>",
  "input": <tool-specific args>,
  "rationale": "<one short sentence>",
  "confidence_score": <float in [0,1], required when tool=finalize>
}

Hard rules:
- DO NOT issue queries containing predicted-outcome phrases:
  ("tenant wins", "compensation £", "maladministration found",
  "service failure upheld"). These are filtered before retrieval and
  count as a wasted iteration.
- DO NOT reference the case_id under analysis.
- Cap: 4 total iterations. You are at iteration {iter}.
```

User (rendered each iteration):
```
Case summary (<=400 words): {case_summary}
Issue type: {issue_type}    Vulnerability: {vuln}    Awaab's: {awaab}

Queries already issued ({n_queries}):
{numbered_list_of_queries_with_purposes}

Top chunks retrieved ({n_chunks}, deduped, by purpose):
{by_purpose: top-3 chunks each, with source_id and 1-line span}

Amounts extracted: {amounts_extracted_or_"none yet"}
KG facts checked:  {kg_facts_seen_or_"none yet"}

Choose ONE action.
```

The system prompt is the **cacheable prefix** ([Anthropic prompt
caching][19]) — we mark it `cache_control: ephemeral` and pay write
cost once per prompt version. The user prompt changes every iteration
but is short (~600 tokens at iter 4), so cache hit-rate on system+rules
should be ≥80% in the steady state.

### 3.3 Termination policy (priority order)

1. **Judge `finalize` with `confidence_score ≥ 0.70`** ⇒ `terminator =
   "judge_ok"`. (LLM-driven primary signal.)
2. **Judge `abstain`** ⇒ `terminator = "judge_abstain"`. (LLM-driven
   abstention — distinct from predictor abstention; logged separately
   per plan §7.2.)
3. **Duplicate `(tool, query)`** ⇒ `terminator = "dup_query"`. (Cycle
   guard — Reflexion-style.)
4. **`MAX_TOKENS = 8000`** ⇒ `terminator = "token_cap"`.
5. **`MAX_CHUNKS = 24`** ⇒ `terminator = "chunks_cap"`.
6. **`MAX_ITER = 4`** ⇒ `terminator = "max_iter"`. (Hard cap.)
7. **Two consecutive judge JSON-validation failures** ⇒ `terminator =
   "judge_invalid"` and fall back to `static_two_pass` (per plan §3.5).

Every path writes a single `terminator` field; the audit gate
(plan §5.4) requires ≥95% of cases hitting one of {`judge_ok`,
`judge_abstain`, `dup_query`}, with `max_iter` and `token_cap`
together capped at ≤5%.

### 3.4 Trace fields — canonical schema

Mirrors OTel GenAI semantic conventions ([OTel SemConv][13]) so we get
free Langfuse / Phoenix interoperability:

```jsonc
// data/eval_artifacts/<run>/agent_traces/<case_id>.json
{
  "trace_id": "uuid",                          // OTel
  "case_id": "housing-ombudsman-202428538",    // ⇒ gen_ai.conversation.id
  "agent_name": "housing_ombudsman_retrieval", // ⇒ gen_ai.agent.name
  "agent_version": "v0.1.0",                   // ⇒ gen_ai.agent.version
  "model": "claude-sonnet-4-6",                // ⇒ gen_ai.request.model
  "iter_count": 3,
  "terminator": "judge_ok",
  "tokens_used": 6240,
  "latency_ms_total": 24800,
  "spans": [
    {
      "span_id": "...", "parent_id": null,
      "operation_name": "agent.run",
      "kind": "agent_run",
      "iter": 0,
      "input": {"case_id": "..."},
      "output": {"terminator": "judge_ok"},
      "latency_ms": 24800,
      "input_tokens": 0, "output_tokens": 0
    },
    {
      "span_id": "...", "parent_id": "<agent.run>",
      "operation_name": "tool.call",
      "kind": "query_plan",
      "tool_name": "query_planner",
      "iter": 1,
      "input": {"issue_type": "damp_mould", ...},
      "output": {"queries": [...], "chunks_added_count": 12},
      "latency_ms": 4200,
      "input_tokens": 820, "output_tokens": 240
    },
    {
      "span_id": "...", "parent_id": "<agent.run>",
      "operation_name": "tool.call",
      "kind": "judge",
      "tool_name": "sufficiency_judge",
      "iter": 2,
      "input": {"state_summary_md": "..."},
      "output": {
        "tool": "extract_amounts",
        "input": {"chunk_id": "ho_202412345#para_47"},
        "rationale": "this is the order paragraph; pull amounts",
        "confidence_score": null
      },
      "latency_ms": 1900,
      "input_tokens": 1850, "output_tokens": 110
    },
    { "...": "..." }
  ],
  "leakage_audit": {
    "all_queries_filter_applied": true,
    "blocked_queries": []
  }
}
```

**Why this schema**:
- Every field maps to a documented OTel `gen_ai.*` attribute or to a
  domain-specific name we own (`leakage_audit`). The plan's existing
  trace example (§3.6) becomes a thin domain wrapper around OTel
  spans.
- `parent_id` lets Langfuse / Phoenix render a tree view without
  custom code.
- `kind` distinguishes query_plan / judge / retrieve / extract_amounts
  / check_kg_fact / finalize within `tool.call` — needed for the
  per-kind metrics in plan §5.4.

### 3.5 Observability — pick one

**Pick: Langfuse (self-hosted, OSS).** Justification:

- Free at our volume; thesis-grade reproducibility (Postgres dump = a
  dataset).
- OpenTelemetry-native via Langfuse OTel ingestion.
- LLM-as-judge is built-in for offline eval (we will use it for the
  sufficiency-judge calibration, not just for prediction
  evaluation).
- Acquired by Clickhouse Jan 2026; capabilities unchanged
  ([Digital Applied 2026][17]) — no abandonment risk in the next 12
  months.

**Phoenix (Arize)** is the credible alternative if we want stronger
out-of-the-box drift / embedding analysis, and is already used by
production legal-AI shops via the OpenAI Agent SDK
([Harvey 2026][16]). Either works; Langfuse wins on simplicity and
LLM-as-judge primitives.

**Do not pick**: LangSmith (vendor lock-in to LangChain we don't use),
Weave (only if already on W&B), Helicone (proxy-style; thinner eval
story).

### 3.6 Tool placement on deterministic ↔ LLM-driven axis

| Tool / step | Pos on axis | Rationale |
|---|---|---|
| `retrieve` query text | **LLM-driven** (judge picks) | The whole point of agentic retrieval. |
| `retrieve` envelope (filters) | **deterministic** | Leakage invariant; must be enforceable in tests. |
| `extract_amounts` | **deterministic primary, LLM fallback** | Regex covers >90% of Ombudsman patterns; LLM only on regex-empty `orders` chunks. Reproducibility wins. |
| `check_kg_fact` | **deterministic** | Typed field reads from a fixed schema; no judgement to make. |
| `finalize` decision | **LLM-driven** | The judge's job. Confidence threshold τ=0.70 is the only deterministic gate. |
| `abstain` decision | **LLM-driven** | Same — but logged distinctly from predictor abstention. |
| Sufficiency judge prompt schema | **deterministic** (Pydantic) | Schema validation is non-negotiable. |
| RRF fusion weights | **deterministic (hardcoded)** | Inductive bias; revisit only if recall analysis says otherwise. |
| Cycle / dedup detection | **deterministic** | A safety property, not a judgement. |
| Cap enforcement | **deterministic** | A safety property. |
| Query safety guard | **deterministic regex** | Audit defensibility; LLM gate would be non-deterministic. |

**Summary**: every *judgement* is LLM-driven; every *invariant* is
deterministic. This is the recommended split.

---

## 4. Open questions

1. **Does `confidence_score` calibrate well for Sonnet 4.6 on legal
   judgement tasks?** EviMem's ρ=0.93 is on conversational memory, not
   legal QA. We should run a 50-case calibration audit on the judge's
   `confidence_score` and decide whether τ=0.70 is right. If ECE
   exceeds 0.10 we apply temperature scaling on the judge before
   trusting the threshold.
2. **Single-call vs multi-turn ablation in L-MARS.** The Simple Mode
   number is missing from public summaries; reading the paper body is
   needed to set our expected delta. The 38pp headline is vs zero-shot
   and overstates the agentic gain.
3. **Does 4 iterations bind?** ReAct used 7 on HotpotQA. If the judge
   medium iter_count saturates near 4 in our smoke tests, we may need
   to extend to 5-6. If it sits at 1-2, we deprecate C entirely
   (per plan §11 thesis-honesty rules).
4. **Should the sufficiency judge see reranker scores?** Reranker
   outputs are deterministic numerical features; passing them to the
   judge gives it a calibrated signal but increases prompt length.
   Worth a one-off A/B once C is wired.
5. **Should we mirror Reflexion's 3-cycle heuristic instead of just
   2-strict dedup?** Reflexion: same action+obs *3 times* triggers
   reflection, not termination. We currently terminate on duplicate.
   The Reflexion path is gentler but adds a code path and a state
   field. Probably not worth it for our 4-iter budget.

---

## 5. References

[1]: https://arxiv.org/abs/2310.11511 "Asai, A., Wu, Z., Wang, Y., Sil, A., Hajishirzi, H. (2024). Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection. ICLR 2024 (oral)."

[2]: https://arxiv.org/abs/2509.00761 "Ni, B., et al. (2025). L-MARS: Legal Multi-Agent Workflow with Orchestrated Reasoning and Agentic Search. arXiv:2509.00761."

[3]: https://github.com/boqiny/L-MARS "L-MARS reference implementation (boqiny/L-MARS, GitHub)."

[4]: https://arxiv.org/abs/2401.15884 "Yan, S.-Q., Gu, J.-C., Zhu, Y., Ling, Z.-H. (2024). Corrective Retrieval Augmented Generation. arXiv:2401.15884."

[5]: https://aclanthology.org/2023.emnlp-main.495/ "Jiang, Z., Xu, F.F., Gao, L., et al. (2023). Active Retrieval Augmented Generation. EMNLP 2023."

[6]: https://openreview.net/forum?id=WE_vluYUL- "Yao, S., Zhao, J., Yu, D., Du, N., Shafran, I., Narasimhan, K., Cao, Y. (2023). ReAct: Synergizing Reasoning and Acting in Language Models. ICLR 2023."

[7]: https://aclanthology.org/2023.acl-long.557/ "Trivedi, H., Balasubramanian, N., Khot, T., Sabharwal, A. (2023). Interleaving Retrieval with Chain-of-Thought Reasoning for Knowledge-Intensive Multi-Step Questions. ACL 2023."

[8]: https://arxiv.org/abs/2303.11366 "Shinn, N., Cassano, F., Gopinath, A., Narasimhan, K., Yao, S. (2023). Reflexion: Language Agents with Verbal Reinforcement Learning. NeurIPS 2023."

[9]: https://arxiv.org/html/2604.27695 "EviMem: Evidence-Gap-Driven Iterative Retrieval for Long-Term Conversational Memory (2026)."

[10]: https://arxiv.org/abs/2306.16092 "Cui, J., et al. (2024). ChatLaw: A Multi-Agent Collaborative Legal Assistant with Knowledge Graph Enhanced Mixture-of-Experts Large Language Model."

[11]: https://arxiv.org/html/2601.06216v1 "LLM Agents in Law: Taxonomy, Applications, and Challenges (2026)."

[12]: https://arxiv.org/pdf/2511.21033 "Towards Trustworthy Legal AI through LLM Agents and Formal Reasoning (2025)."

[13]: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/ "OpenTelemetry Semantic Conventions for GenAI agent and framework spans (March 2026, experimental)."

[14]: https://arxiv.org/html/2509.00761 "L-MARS HTML rendering (multi-turn vs simple mode)."

[15]: https://dho.stanford.edu/wp-content/uploads/Legal_RAG_Hallucinations.pdf "Magesh, V., Surani, F., Dahl, M., Suzgun, M., Manning, C., Ho, D. (2025). Hallucination-Free? Assessing the Reliability of Leading AI Legal Research Tools. Stanford DHO."

[16]: https://www.harvey.ai/blog/how-agentic-search-unlocks-legal-research-intelligence "Harvey AI (2026). How Agentic Search Unlocks Legal Research Intelligence."

[17]: https://www.digitalapplied.com/blog/agent-observability-platforms-langsmith-langfuse-arize-2026 "Digital Applied (2026). Agent Observability: LangSmith, Langfuse, Arize 2026."

[18]: https://langwatch.ai/blog/best-ai-agent-frameworks-in-2025-comparing-langgraph-dspy-crewai-agno-and-more "LangWatch (2025). Best AI Agent Frameworks: comparing LangGraph, DSPy, CrewAI, Agno."

[18b]: https://lukedinh1501.medium.com/i-built-the-same-ai-agent-twice-heres-why-dspy-and-langgraph-are-nothing-alike-b0eac26a57a6 "Dinh, L. (2025). I Built the Same AI Agent Twice — DSPy vs LangGraph."

[19]: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching "Anthropic. Prompt Caching documentation."
