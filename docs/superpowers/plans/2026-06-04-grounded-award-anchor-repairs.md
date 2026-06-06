# Grounded Award Anchor for Repairs (RQ2) — Implementation Plan

> **For agentic workers:** executed inline this session. Steps use `- [ ]`.

**Goal:** Make the repairs predictor always emit a settlement amount (grounded in retrieved comparator awards where present, free LLM estimate otherwise) and evaluate it as a 4-arm ablation against the median-award baseline, so RQ2's degenerate ZOPA becomes a measured, non-degenerate result.

**Architecture:** The always-predict policy is already implemented behind env flags (`STREAM_C_NO_RAG_PREDICT_AMOUNTS` for no-RAG, `STREAM_C_ALWAYS_PREDICT_AMOUNTS` for RAG). New work: (C1) surface comparator £ figures into the repairs prompt for salience; (C3) rewrite the RQ2 harness to run retrieval/KG arms async-safely (reusing `predict_all.py` construction helpers, NOT its sync `_live_call`), with corrected metrics, grounding labels, paired bootstrap CIs, and retrieval logging.

**Tech stack:** Python 3.11 venv, OpenAI gpt-5.5, ChromaDB+BM25 index at `indices/housing_repairs_social_v1/`, pytest.

---

## Arms (env-flag driven, NO predictor change for the policy)

| Arm | mode | flags |
|---|---|---|
| `legacy_llm_only_strict` | llm_only | none (current degenerate control) |
| `llm_only_always_predict` | llm_only | `STREAM_C_NO_RAG_PREDICT_AMOUNTS=1` |
| `rag_only_always_predict` | rag_only | `STREAM_C_ALWAYS_PREDICT_AMOUNTS=1` |
| `hybrid_always_predict` | hybrid | `STREAM_C_ALWAYS_PREDICT_AMOUNTS=1` |

Corpus: `data/gold_standard/housing_repairs_social_v2_strict_clean.jsonl` (n=48). Index: present at `indices/housing_repairs_social_v1/research_seed_2026_05/`.

## Addressed review points
1. Confound → 4 arms above (policy separated from retrieval/KG).
2. `amount_anchor_source` → derived in the runner from `retrieval_evidence` (no fragile schema/LLM-emit dependence); documented as a retrieval-side coverage signal.
3. ZOPA path → explicit unit test through `OutputAssembler` → top-level `predicted_settlement_range` → `compute_zopa` (deposit=None ⇒ `deposit_cap=inf`, range `(0.85a,1.15a)`).
4. Async trap → build pipeline/KG/engine inline and `await engine.predict(...)`; never call `predict_all._live_call` (it does `asyncio.run`).
5. Anchored fallback → `comparator_median_gbp` recorded only where comparators carry £ (null otherwise) + coverage; LOO median (plain + temporal where dates present) are the disciplined baselines.
Eval fixes → `zopa_found_rate` demoted to coverage; add `actual_within_zopa`, `zopa_width`, over/under rate; disaggregate amount metrics by `amount_anchor_source`; paired bootstrap CI on model−baseline; log retrieved source IDs / £-amount source IDs / dup chunks / leakage status.

## Task 1 — `_extract_award_amounts` helper (TDD)
**Files:** Modify `packages/llm_orchestrator/pipeline/issue_predictor.py`; Test `packages/llm_orchestrator/tests/test_award_amount_extraction.py`.
- [ ] Test: `£500`→[500.0]; `£1,200.50`→[1200.5]; `1500 pounds`→[1500.0]; `compensation of £450 and £75`→[450.0,75.0]; `no money here`→[]; bare `£`→[].
- [ ] Implement `_extract_award_amounts(text: str) -> list[float]` (regex `£\s?[\d,]+(?:\.\d{1,2})?` and `\d[\d,]*\s?(?:gbp|pounds)`), strip commas, dedupe-preserve-order, drop 0.
- [ ] Run test green.

## Task 2 — C1: surface comparator £ figures in repairs RAG prompt
**Files:** Modify `issue_predictor.py:577-587` (the `formatted_cases` loop in `_predict_issue`).
- [ ] After `amount_line`, compute `amts = _extract_award_amounts(str(text))` and build `award_values_line = f"\nComparator award figures: {', '.join('£'+format(a,',.0f') for a in amts[:4])}"` when `amts` else `""`. Append to the case block. (Pure prompt-string change; no schema/construction change.)
- [ ] Quick import/smoke: `python -c "import llm_orchestrator.pipeline.issue_predictor"`.

## Task 3 — ZOPA-path unit test (review point 3)
**Files:** Test `packages/llm_orchestrator/tests/test_zopa_amount_path.py`.
- [ ] Build a minimal `OutputAssembler().assemble(...)` (or reuse existing fixtures) for a repairs CaseFile with `tenancy.deposit_amount=None`, one issue `outcome=TENANT_WINS, predicted_amount=500.0`. Assert `result.predicted_settlement_range == (425.0, 575.0)` and `result.tenant_recovery_amount == 500.0`.
- [ ] Feed `result` to `compute_zopa`; assert `center==500.0`, `max>min>0` (non-degenerate).
- [ ] Also assert an `outcome=UNCERTAIN` issue with `predicted_amount=500` yields `predicted_settlement_range is None` (documents the uncertain-skip caveat).

## Task 4 — C3: harness rewrite (the bulk)
**Files:** Modify `scripts/eval/rq2_settlement_fairness.py`.
- [ ] Import construction helpers from `scripts.eval.predict_all`: `_select_namespace, _rag_config_for_namespace, _ensure_rag_index_exists, _decision_date_coverage, _build_eval_retrieval_filter, _EvalFilteredRAGPipeline, _build_eval_knowledge_graph`; `RAGPipeline` from `rag_engine.pipeline`.
- [ ] Add a cached `_build_pipeline(gold_case, rag_index_root)` replicating `_pipeline_for` (namespace→cfg→ensure→RAGPipeline→date coverage).
- [ ] In the per-case loop: for `rag_only`/`hybrid` build `_EvalFilteredRAGPipeline(rag, filters, requesting_namespace=ns)`; for `hybrid` build KG via `_build_eval_knowledge_graph`; construct `PredictionEngineV2(llm_client, rag_pipeline, prompt_pack)` and `await engine.predict(case_file, knowledge_graph=kg, top_k, mode, matter_type)`. (No `asyncio.run`.)
- [ ] Per-case row additions: `amount_anchor_source` (comparator if any retrieved `text_preview` carries £ else free_estimate), `comparator_count`, `comparator_median_gbp`, `zopa_min/max/center/width`, `zopa_found`, `actual_within_zopa`, `over_under` (sign settlement−actual), `predicted_amount`, `justification` (first issue reasoning ≤300 chars), `retrieved_source_ids`, `amount_source_ids`, `dup_chunk_count`, `leakage_excluded_count`, `leakage_ok`.
- [ ] Summary additions: keep model/settlement/baseline blocks; demote `zopa_found_rate` to coverage; add `grounding_mix`, disaggregated settlement metrics by `amount_anchor_source`, paired bootstrap delta (baseline_MAE − settlement_MAE; within20 delta) via a local `_paired_bootstrap(seed=42)`; add temporal-LOO median baseline block when ≥90% cases carry `decision_date` else note skipped.
- [ ] `--arm` label + per-arm out dir `data/eval_artifacts/runs/rq2_repairs_<arm>_FINAL/`.
- [ ] Smoke: `--mode rag_only --arm rag_only_always_predict --limit 3` with `STREAM_C_ALWAYS_PREDICT_AMOUNTS=1`; assert ≥1 `zopa_found` true; eyeball justification + grounding.

## Task 5 — Run the 4 arms (background) and verify
- [ ] Run all four arms full (n=48) to fixed out-dirs; 0 errors; inspect summaries.
- [ ] Sanity: legacy arm reproduces ~0 ZOPA; always-predict arms have zopa_found_rate>0; check whether any arm's settlement beats the LOO baseline (report honestly either way).

## Task 6 — Report update (after results)
- [ ] `evaluation.tex` §RQ2 + `tab:eval-rq2`: 4-arm ablation, grounding mix, paired-CI deltas, the deliberate cite-or-abstain relaxation for the quantum.
- [ ] `mediation.tex` med-zopa/med-eval-design; `abstract.tex` sentence (new outcome); scorecard row; threats; conclusion future-work item 1.

## Risks
Grounded amount may still lose to baseline (report honestly). Free-estimate fallback reintroduces ungrounded figures (labelled + framed). Soft grounding = model reading £ from retrieved text. Cost/time: 4×~48 predictions, rag/hybrid heavier — run in background.
