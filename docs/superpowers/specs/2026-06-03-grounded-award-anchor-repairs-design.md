# Grounded Award Anchor for Repairs Mediation (RQ2) — Design

**Date:** 2026-06-03
**Status:** Design approved in brainstorming; pending spec review.
**Owner:** Mohamed
**Related:** RQ2 negative result (`Proposer-Final-Report/evaluation/evaluation.tex` §`sec:eval-rq2`), measured 2026-06-02; future-work item 1 in `conclusion/conclusion.tex` ("non-deposit award anchor").

## 1. Problem

RQ2 currently returns a measured negative result: the mediator's Zone of Possible Agreement (ZOPA) is **award-anchored**, so when the predictor emits no monetary amount the ZOPA collapses to a zero-width range and the proposed settlement is £0. Measured on repairs (n=48) and employment (n=50): **0% non-degenerate ZOPA, 0 monetary quantum predicted**; the settlement never beats the leave-one-out median-award baseline (loses outright on repairs, ties the itself-degenerate baseline on employment).

Root cause: `compute_zopa` (`packages/llm_orchestrator/tools/mediator/_calculations.py:18-44`) keys only off `predicted_settlement_range` → `tenant_recovery_amount` → `deposit_at_stake`, else `{0,0}`. Under `llm_only` (no retrieval) the predictor has no comparator awards to anchor on and is instructed to set `predicted_amount=null`, so every monetary field is `None` → degenerate.

## 2. Goal

Make the **repairs** predictor **always** emit a settlement amount, anchored to retrieved comparator awards where they exist, so the ZOPA is non-degenerate. Then evaluate whether that settlement aligns with actual awards better than the median-award baseline, as an ablation (`llm_only` → `rag_only` → `hybrid`).

## 3. Scope

**In scope:** housing repairs only (it has a built RAG index at `indices/housing_repairs_social_v1/research_seed_2026_05/`).

**Out of scope (future work):**
- Employment grounding — no RAG index exists; requires scrape → ingest → index of ET decisions (multi-day, SHA-65 incomplete). Employment stays the blocked/degenerate case in the report.
- Hard structured-amount grounding (add `awarded_gbp` to `SourceMetadata` + extractor + full reindex).
- Any change to cite-or-abstain for **legal citations / determinations** — unchanged.

## 4. Locked decisions

1. **Grounded-by-comparables, soft grounding.** Surface the £ figures already present in retrieved chunk text into the prompt; no reindex.
2. **Always predict a settlement amount** — no abstaining on the quantum. When no retrieved comparator carries a figure, the fallback is a **free LLM estimate** from the case facts (the author's explicit choice).
3. **Integrity guardrails (mandatory, cheap):**
   - Cite-or-abstain stays intact for legal claims and citations; relaxed **only** for the settlement quantum (negotiation information, not asserted legal authority). Stated explicitly in the report.
   - **Per-case grounding label:** `comparator` vs `free_estimate`.
   - **Anchored-fallback shadow number:** for every case also record the median of retrieved comparator awards, so the report can compare the free estimate against a disciplined anchor side by side.
4. **Evaluation = ablation** on repairs (n=48): `llm_only` (control / current degenerate result) → `rag_only` → `hybrid` (RAG+KG, the RQ1 flagship), each scored against the leave-one-out median-award baseline.

## 5. Changes

### C1 — Surface comparator award figures into the prompt
`packages/llm_orchestrator/pipeline/issue_predictor.py` (~550-587, the `formatted_cases` loop).
- Add `_extract_award_amounts(text)` extending the existing `_contains_award_amount` regex to return the £ value(s).
- Render `Comparator award: £X` per retrieved comparable (replacing the boolean "Award amount signal: present").
- Accumulate the comparator amounts for the issue (consumed by the anchored-fallback shadow number and the prompt).

### C2 — Always-predict instruction + grounding label
`issue_predictor.py` (repairs user-prompt amount clause ~1291-1306; amount parsing ~870-902) and `packages/llm_orchestrator/prompts/packs/housing_repairs_social_v1.py` (system prompt ~88-95).
- Change the instruction from "set `predicted_amount` to null when no comparator amount" to: **"Always produce `predicted_amount`. If retrieved comparators carry award/remedy figures, estimate from them and justify it (which comparators, what range). If none do, give your best reasoned estimate from the case facts and flag it as ungrounded."**
- Emit/record `amount_grounding ∈ {comparator, free_estimate}` (derive from whether any comparator amount was available for the issue).
- Do **not** use the `STREAM_C_ALWAYS_PREDICT_AMOUNTS` flat-£400/band-midpoint flag.

### C3 — RQ2 harness with retrieval + KG, ablation, extra columns
`scripts/eval/rq2_settlement_fairness.py`.
- Wire RAG (+KG for hybrid) by reusing `scripts/eval/predict_all.py`'s `_live_predict_fn_factory` (it already builds the namespaced `RAGPipeline`, the eval leakage filter `_EvalFilteredRAGPipeline`, and the KG for hybrid). Replace the hard-wired `rag_pipeline=None`. Accept `--mode llm_only|rag_only|hybrid`.
- Per-case rows: add `amount_grounding`, `comparator_count`, `comparator_median_gbp` (anchored-fallback), and a short `justification` snippet from the prediction reasoning.
- Summary: keep existing blocks; ensure `zopa_found_rate` (expected > 0 now), add `grounding_mix` (% comparator vs free), and add a fourth score block `anchored_fallback_settlement` (ZOPA centre computed with the comparator-median substituted on free-estimate cases) so the report compares free vs anchored honestly.
- Output dirs: `data/eval_artifacts/runs/rq2_settlement_repairs_{llm_only,rag_only,hybrid}_FINAL/`.

## 6. Evaluation design

- **Corpus:** `data/gold_standard/housing_repairs_social_v2_strict_clean.jsonl` (n=48) — same gold as the current RQ2 run, for comparability.
- **Arms:** `llm_only` (control), `rag_only`, `hybrid`.
- **Per arm, scored vs leave-one-out median-award baseline:** `zopa_found_rate`, within ±20%, within £100, MAE, median AE, coverage, grounding mix; plus the anchored-fallback settlement block.
- **Leakage control:** reuse the predict_all eval filter (never retrieve the case's own source).
- **Honest reporting:** report whatever it shows; disaggregate `comparator`-grounded vs `free_estimate` alignment. A non-degenerate-but-still-loses result is acceptable and still a stronger thesis result than the current "never tested with retrieval".

## 7. Report changes (after the run)

- `evaluation/evaluation.tex` §`sec:eval-rq2` + `tab:eval-rq2`: replace the single `llm_only` result with the 3-arm ablation; add the grounding mix; state the deliberate cite-or-abstain relaxation for the quantum.
- `mediation/mediation.tex` (`sec:med-zopa`, `sec:med-eval-design`): describe the grounded award anchor, the always-predict policy, and the integrity scoping.
- `abstract/abstract.tex`: swap the ZOPA sentence for the new measured outcome (drafted only after the run — no pre-claiming).
- `tab:eval-scorecard` RQ2 row + Threats to Validity: update.
- `conclusion/conclusion.tex` future-work item 1: note partially addressed for repairs; employment remains.

## 8. Testing

- **Unit (prompt assembly):** given a retrieved comparator carrying "£500", the repairs prompt surfaces `Comparator award: £500`; `_extract_award_amounts` parses values; `amount_grounding` label is correct.
- **Unit (ZOPA):** a non-null `predicted_amount` yields a non-degenerate `compute_zopa` (extend existing `test_mediator_tools.py` if not already covered).
- **Smoke:** `rq2_settlement_fairness.py --mode rag_only --limit 3` on repairs; assert `zopa_found` flips True on ≥1 case; eyeball the justification + grounding label.
- **Regression:** existing `test_tribunal_costs.py`, `test_mediator_tools.py`, predictor tests stay green.

## 9. Risks / honest caveats (to land in the report)

- Grounded amount may still not beat the median baseline (quantum is the system's weakest axis) — reported honestly.
- Free-estimate fallback reintroduces ungrounded figures — mitigated by the grounding label, the anchored-fallback comparison, and explicit report framing; residual viva risk acknowledged.
- Soft grounding = the model reading £ from retrieved text, not a verified structured join — framed as such.
- Retrieval quality is mediocre (~34% orphaned chunks) and may cap grounding/coverage.
- Cost/time: ~48 cases × 3 arms; `rag_only`/`hybrid` are heavier than `llm_only`. Run in the background; record provenance.

## 10. Effort

Code + tests ≈ half day; runs ≈ 1-2h (3 arms, background); report ≈ 1-2h. Comfortably inside the 12 June deadline.
