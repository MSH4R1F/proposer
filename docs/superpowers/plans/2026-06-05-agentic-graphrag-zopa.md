# Agentic GraphRAG ZOPA Predictor — Implementation Plan

> Executed inline. Steps use `- [ ]`.

**Goal:** A tool-calling agent that reads the case KG, factor-shapes its comparator search, reads real ordered amounts, and converges on a grounded ZOPA — wired as `RetrievalStrategy.AGENTIC_PREDICT` (under `mode=hybrid`). Beat the median-award baseline on RQ2 repairs.

**Architecture:** Self-contained agent loop (drives `ToolSet.dispatch` directly, reads verdict off a `ToolContext` subclass — the `retrieval_agent_loop` pattern, NOT `AgentLoop`, which only returns `final_text`). Reuses `retrieve` + `extract_amounts`; adds `list_case_factors`, `retrieve_by_factor_overlap`, `finalize_prediction`. Engine branch builds `IssuePrediction`s → `OutputAssembler`, then overrides `predicted_settlement_range` with the agent's bounds.

**Tech:** Python 3.11, OpenAI gpt-5.5 `run_agent_turn`, ChromaDB+BM25 index, pytest.

---

## File map
- Modify `packages/llm_orchestrator/models/prediction_v2.py` — add `RetrievalStrategy.AGENTIC_PREDICT`.
- Create `packages/llm_orchestrator/pipeline/agentic_predictor.py` — context, 3 tools, toolset, `AgenticPredictor` (+loop + system prompt).
- Modify `packages/llm_orchestrator/pipeline/retrieval_agent_tools.py` — make `_read_kg_fact` read `kg.factor_assertions` (so reused `check_kg_fact` is real; backward-safe since current callers pass `kg=None`).
- Modify `packages/llm_orchestrator/pipeline/prediction_engine_v2.py` — `_agentic_predict` branch + `gold_case_id` kwarg.
- Modify `scripts/eval/rq2_settlement_fairness.py` — `--mode agentic` sugar.
- Tests: `packages/llm_orchestrator/tests/test_agentic_predictor.py`.

## Task 1 — enum + finalize tool/context (TDD)
- [ ] Add `AGENTIC_PREDICT = "agentic_predict"` to `RetrievalStrategy`.
- [ ] In `agentic_predictor.py`: `AgenticPredictContext(RetrievalToolContext)` with `verdict: Optional[dict] = None`.
- [ ] `FinalizePredictionArgs(BaseModel)`: outcome `Literal["tenant_wins","landlord_wins","split","uncertain"]`, determination `Optional[str]`, predicted_amount `float`, low `float`, high `float`, confidence `float`, rationale `str`, comparator_source_ids `list[str]`, comparator_amounts `list[float]`, kg_factors_used `list[str]`.
- [ ] `@tool finalize_prediction(ctx: ToolContext, args)` → cast to `AgenticPredictContext`, set `ctx.verdict = args.model_dump()`, return `{"status":"recorded"}`.
- [ ] Test: dispatch finalize through a ToolSet sets `ctx.verdict`. Run green.

## Task 2 — list_case_factors + retrieve_by_factor_overlap
- [ ] `list_case_factors(ctx, args: EmptyArgs)` → read `ctx.kg.factor_assertions` (guard None), return `{factors:[{factor_id,label,supported}]}` (label = factor_id humanized).
- [ ] `retrieve_by_factor_overlap(ctx, args: FactorOverlapArgs{factor_ids:list[str], section_type:Optional[Literal[...]]="decision", k:int=5})` → build query from issue + factor labels, `assert_query_safe`, call `_call_rag_retrieve(ctx.rag, query, k, section_type)`, `state.add_chunks(_to_agent_chunk(...))`. Reuse helpers imported from `retrieval_agent_tools`.
- [ ] `build_agentic_predict_toolset()` → ToolSet {retrieve, extract_amounts, list_case_factors, retrieve_by_factor_overlap, finalize_prediction}.
- [ ] Test: toolset builds; schemas_for(OPENAI) returns 5 tools. Green.

## Task 3 — AgenticPredictor loop + system prompt
- [ ] `AgenticPredictor(llm_client, provider)`. `async predict_issue(case_file, issue, rag, knowledge_graph, gold_case_id, max_turns=8) -> IssuePrediction`.
- [ ] Build `AgenticPredictContext(rag=rag, kg=knowledge_graph, agent_state=AgentState(case_id, issue_type.value), gold_case_id=...)`.
- [ ] Custom loop: per turn `run_agent_turn(system, messages, schemas)`; append assistant blocks; dispatch each tool_use via toolset; append tool_result blocks; break on no tool_use (end_turn) OR `ctx.verdict is not None`.
- [ ] Build `IssuePrediction` from `ctx.verdict` (outcome, predicted_determination, predicted_amount, amount_range=(low,high), raw_confidence, reasoning=rationale, supporting_cases=[Citation(case_reference=s, year=0, quote="", relevance="comparator", verified=False) for s in comparator_source_ids]).
- [ ] Fallback (no verdict): median of `state.amounts_extracted` → amount; else outcome=uncertain, amount=None.
- [ ] System prompt per spec §3d.
- [ ] Smoke test (mocked client) that a scripted finalize produces the IssuePrediction. Green.

## Task 4 — engine branch + gold_case_id
- [ ] `predict(..., gold_case_id: str = "")` kwarg.
- [ ] Before Step 3, `if strategy == RetrievalStrategy.AGENTIC_PREDICT:` → `_agentic_predict(case_file, knowledge_graph, gold_case_id, matter_type, metadata)`: decompose issues (reuse), per issue `AgenticPredictor.predict_issue`, `output_assembler.assemble(...)`, then set `result.predicted_settlement_range = (min lows, max highs)` from verdicts; return.
- [ ] Require `self.rag` (raise clear error if None).

## Task 5 — _read_kg_fact reads factor_assertions
- [ ] Update `_read_kg_fact(kg, field)`: if `kg` has `factor_assertions`, map `field`→assertion presence/value; else existing `read_typed_fact` path; else `(None, False)`.

## Task 6 — harness --mode agentic
- [ ] In `rq2_settlement_fairness.py`: accept `--mode agentic`; set `mode=HYBRID, retrieval_strategy=AGENTIC_PREDICT, needs_rag=needs_kg=True`; pass `retrieval_strategy=` + `gold_case_id=g.case_id` to `engine.predict`. Build engine with `rag_pipeline` set (the agentic path reads `self.rag`).

## Task 7 — smoke + partial eval + report
- [ ] Smoke `--mode agentic --limit 3`; assert verdict set, settlements varied/grounded, leakage_ok.
- [ ] Partial eval (--limit 20) to gauge vs baseline before full n=48.
- [ ] Full n=48 if promising; update report (new `agentic` arm in tab:eval-rq2 + narrative).

## Risks
~5–10 LLM calls/case (smoke small first); may not beat baseline (report honestly); leakage via eval-filtered RAG wrapper (assert in logs).
