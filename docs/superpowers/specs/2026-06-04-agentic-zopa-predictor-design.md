# Agentic GraphRAG ZOPA Predictor — Design

**Date:** 2026-06-04 (rev 2026-06-05)
**Status:** Design + review findings integrated; pending final spec review.
**Thesis framing:** *Agentic GraphRAG for legally grounded award prediction.*
**Goal:** Replace single-pass amount prediction with an iterative, tool-calling agent that (a) reads the case **knowledge graph** as memory, (b) uses graph factors to shape comparator **retrieval**, (c) reads the real **ordered amounts** from comparable decisions, and (d) converges on a grounded final ZOPA that **cites both graph and text**. Target: beat the leave-one-out median-award baseline on RQ2 award alignment (housing repairs, n=48).

## 1. Wiring decision (review P1)

`agentic` is added as a **`RetrievalStrategy.AGENTIC_PREDICT`** invoked with **`mode=PredictionMode.HYBRID`** (so the existing `needs_rag`/`needs_kg` gates pass and RAG+KG are visible). Rationale: a naive new `PredictionMode` would require updating every mode gate; the strategy path is the shortest safe route. The RQ2 harness accepts `--mode agentic` as sugar that sets `mode=HYBRID, retrieval_strategy=AGENTIC_PREDICT` and forces `needs_rag=needs_kg=True`.

- Add `AGENTIC_PREDICT = "agentic_predict"` to `RetrievalStrategy` (`models/prediction_v2.py:74`).
- In `PredictionEngineV2.predict(...)`, before the normal retrieval/predict, branch: `if effective_strategy == AGENTIC_PREDICT: return await self._agentic_predict(case_file, rag_pipeline, knowledge_graph, gold_case_id, matter_type)`.
- Thread a new optional `gold_case_id: str = ""` kwarg through `predict()` for eval leakage logging.

## 2. Reuse (≈75%)

- **`AgentLoop`** (`agent_loop/loop.py`) — generic driver. **Modify (review P1):** add `terminal_tool_names: set[str] = frozenset()` ctor param; in the dispatch path, after running tools, if any executed tool name is in `terminal_tool_names`, stop with reason `TERMINAL_TOOL` and return. Keeps `MediatorAgent` behaviour unchanged (empty set).
- **`run_agent_turn`** on both clients (OpenAI gpt-5.5; no forced `tool_choice` needed).
- **`retrieve`** tool (`pipeline/retrieval_agent_tools.py:294`) — reuse; it calls `ctx.rag.retrieve`, so leakage is inherited from the wrapper we pass (review P1).
- **`extract_amounts`** tool (`:372`) — returns each £ with surrounding sentence; the agent judges which is the order. Reuse.
- **`check_kg_fact`** tool (`:425`) — reuse, but its `_read_kg_fact` must be implemented for repairs (see §4).
- **`@tool`/`ToolSet`**, **`RetrievalToolContext`** pattern (`ctx: ToolContext` + runtime-cast — review P2), **`OutputAssembler`** (with the ±15% override fix, §3c).

## 3. Build (net-new)

### 3a. Tools (`pipeline/agentic_predict_tools.py`, new)
All take `ctx: ToolContext` and runtime-cast to `AgenticPredictContext` (subclass of `RetrievalToolContext` adding `knowledge_graph`, `verdict` slot, `kg_facts_seen`, `factor_ids_seen`):
- **`list_case_factors()`** → the case KG's asserted factor ids + human labels (from `knowledge_graph.factor_assertions`). Records into `factor_ids_seen`.
- **`retrieve_by_factor_overlap(factor_ids: list[str], section_type="decision", k=5)`** → KG-driven retrieval: expand the query with the human-readable labels of `factor_ids` and call the **eval-filtered** `ctx.rag.retrieve(...)` (chunk-RAG, leakage-clean). NOT the proposition-store path (which returns 0 award-bearing comparators). Records `factor_ids_seen`.
- **`finalize_prediction(outcome, determination, predicted_amount, low, high, confidence, rationale, comparator_source_ids: list[str], comparator_chunk_ids: list[str], comparator_amounts: list[float], kg_factors_used: list[str])`** → stores a structured verdict on `ctx.verdict`; it is the **terminal tool**. Carries citations (review P2) so cite-or-abstain holds.

### 3b. Agent class `AgenticPredictor` (`agents/agentic_predictor.py`, new, ~70 lines; template `MediatorAgent`)
- `async predict_issue(case_file, issue, rag, knowledge_graph, gold_case_id) -> IssuePrediction`.
- Builds `AgenticPredictContext(rag=<eval-filtered wrapper>, agent_state=AgentState(), gold_case_id=..., knowledge_graph=...)`.
- `AgentLoop(llm_client, tool_set={list_case_factors, check_kg_fact, retrieve, retrieve_by_factor_overlap, extract_amounts, finalize_prediction}, max_turns=8, terminal_tool_names={"finalize_prediction"}, provider=...)`.
- System prompt §3d; user message = the case/issue facts.
- On terminal verdict → build `IssuePrediction(outcome, predicted_determination, predicted_amount, amount_range=(low,high), raw_confidence=confidence, reasoning=rationale, supporting_cases=[Citation(case_reference=src, verified=False) for src in comparator_source_ids])`.
- Fallback (no finalize by `max_turns`): median of `AgentState.amounts_extracted`; if none, `outcome=uncertain, amount=None` (honest abstain).

### 3c. Engine branch `_agentic_predict` (in `prediction_engine_v2.py`)
- Decompose issues (reuse existing decomposition), run `AgenticPredictor.predict_issue` per issue, `OutputAssembler.assemble(...)`.
- **Review P2 (preserve bounds):** after assemble, for the single-issue repairs case set `result.predicted_settlement_range = (low, high)` from the agent verdict (do not let the ±15% rule overwrite the agent's ZOPA). For multi-issue, sum/merge bounds.
- Require `rag_pipeline` (agentic needs search) — raise a clear error if missing.

### 3d. System prompt (the "consistently look and predict" rewrite)
Instruct: you predict the likely compensation award for this housing case. First read the case's structured facts — call `list_case_factors` and `check_kg_fact` for severity, duration, vulnerability, prior-offer facts. Use those factors to search for comparable decisions (`retrieve_by_factor_overlap`, and `retrieve` to refine), focusing on `decision`/orders sections. Call `extract_amounts` to read the **actual ordered totals**; from each amount's surrounding sentence, judge which is the genuine compensation order (ignore rent/arrears/offered figures). Estimate the most likely total for THIS case's severity/duration, anchored within the comparator orders — do not lowball, do not exceed the comparator range without a graph-grounded reason. Then call `finalize_prediction` citing the comparator sources, the amounts used, and the KG factors that drove the estimate. Abstain only if no comparable order can be found.

## 4. `_read_kg_fact` for repairs (review: KG actually used)
Implement the `check_kg_fact` backend to read repairs factor assertions from the case KG: map a fact name (e.g. `vulnerability_flag`, `report_to_first_attendance_days`, `outstanding_works_at_complaint_close`) to the corresponding `factor_assertion` value/evidence on `knowledge_graph`. Return `{present: bool, value, evidence_span}`. The KG is the sidecar-hydrated graph (built via `_build_eval_knowledge_graph(..., factor_assertion_sidecar=...)`), passed through (NOT `kg=None`).

## 5. Evaluation
- RQ2 harness: `--mode agentic` → `mode=HYBRID, retrieval_strategy=AGENTIC_PREDICT`; build the **eval-filtered** `rag_pipeline` (as for hybrid) + the KG (sidecar), call `engine.predict(..., mode=HYBRID, retrieval_strategy=AGENTIC_PREDICT, knowledge_graph=kg, gold_case_id=g.case_id)`.
- Score `finalize` centre vs the median baseline with existing metrics + paired bootstrap. **Log per case:** `agent_turns`, `queries`, `kg_facts_seen`, `factor_ids_seen`, `comparator_source_ids`, `comparator_amounts`, and assert no retrieved id == gold id (leakage check).
- New arm `agentic_v1`; compare vs legacy / rag_only / hybrid (v2) and the baseline.

## 6. Risks / honest notes
- **Cost/latency:** ~5–10 LLM calls/case → smoke on 3–5 first; bounded by `max_turns=8` + token cap.
- **May still not beat baseline** — reported honestly.
- **KG honesty:** the gate fires only with `STREAM_C_KG_GATE_RELAXED` (synthesises some counts); the graph tools read **real** sidecar factor assertions, so the agent's KG use is genuine even though the gate is relaxed. State this.
- **Leakage:** inherited from `_EvalFilteredRAGPipeline`; logged + asserted.
- **Provider:** OpenAI gpt-5.5; the Claude-only forced-`tool_choice` `retrieval_agent_loop.py` is NOT used.

## 7. Out of scope (YAGNI for v1)
`get_factor_evidence`, `find_counterexamples`, `get_timeline_summary` (deferred); multi-issue trade-off bargaining; employment domain; promoting `AGENTIC_PREDICT` to a standalone `PredictionMode`.
