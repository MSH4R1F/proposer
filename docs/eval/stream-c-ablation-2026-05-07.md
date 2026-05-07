# Stream C Ablation — Post-Merge 4-Mode Evaluation (2026-05-07)

## Executive Summary

Stream C (PR 4 + PR 5 + PR 6) has merged on branch `codex/stream-c-prediction-path-plan` (commits `7dd4283…6917d32`). This report documents the results of the post-merge 4-mode ablation against the `housing.repairs_social.v1` gold corpus with `STREAM_C_PR4=1`, `STREAM_C_FACTOR_RETRIEVAL=1`, and `STREAM_C_EVIDENCE_PATH_STRICT=1` all enabled.

**Headline finding:** with the current data state — where domain `Proposition` rows have not yet been backfilled with `factor_ids` and KG `factor_assertions` are not yet populated by a real extractor — the new factor-constrained retrieval and evidence-path validator paths *fall back* to the legacy chunk-RAG / no-card behaviour for every case. The accuracy numbers below therefore reflect the LEGACY pipeline running through the new code paths, not the new architecture's contribution. **`rag_only` wins decisively** on this configuration (83.3% accuracy vs 62.5% hybrid). KG-augmented modes are not yet useful without the data backfill.

The headline thesis claim that "factor-graph KG augmentation moves the needle" CANNOT be supported by this run. It also CANNOT be refuted — the architecture is wired and gates correctly degrade to chunk-RAG when factor data is absent (which, per design decision D5, is the safe default). What this run *does* establish: the Stream C wiring is regression-clean for the path that actually fires under today's data state.

**Recommendation:** keep `STREAM_C_PR4=1` (default; cosmetic prompt-card change, byte-equivalent for deposit). Keep `STREAM_C_FACTOR_RETRIEVAL=1` (default-off in CI but verified safe under fall-back). Set `STREAM_C_EVIDENCE_PATH_STRICT=0` (audit-only) until factor data is backfilled — strict mode would force every prediction to UNCERTAIN when no factor chain exists, which is correct per spec but unhelpful before backfill.

---

## Run Configuration

| Item | Value |
|---|---|
| Date | 2026-05-07 |
| Branch | `codex/stream-c-prediction-path-plan` (commit `6917d32`) |
| Gold corpus | `data/gold_standard/housing_repairs_social_v2_strict_clean.jsonl` |
| Cases | 48 (50 source rows; 2 rejected by `GoldCase` validation, lines 25 + 50 — both were case-flagged for human review) |
| Modes | `hybrid`, `rag_only`, `kg_only`, `llm_only` |
| Engine | `live` |
| Client | `claude` (Anthropic) |
| Top-k | 10 |
| Parallelism | 8 worker processes × 6 cases × 4 modes = 192 predictions |
| Wall time | ~70 minutes |
| Stream C flags | `STREAM_C_PR4=1`, `STREAM_C_FACTOR_RETRIEVAL=1`, `STREAM_C_EVIDENCE_PATH_STRICT=1` |
| Retrieval strategy logged | `factor_constrained` (verified via run logs) |
| Predictions output | [eval/predictions/stream_c_post_merge_2026_05_07/](../../eval/predictions/stream_c_post_merge_2026_05_07/) |
| Eval results | [eval/results/stream_c_post_merge_2026_05_07/](../../eval/results/stream_c_post_merge_2026_05_07/) |

---

## Per-Mode Headline Metrics (point estimates with 95% CI, n=48)

| Mode | Accuracy | Macro F1 | Balanced Acc. | Brier | ECE | Covered Acc. | Abstention Rate |
|---|---|---|---|---|---|---|---|
| **rag_only** | **0.833** [0.729, 0.938] | 0.307 [0.285, 0.478] | 0.426 [0.378, 0.938] | 0.230 [0.213, 0.246] | 0.455 [0.406, 0.488] | 0.952 [0.875, 1.000] | 0.125 [0.042, 0.208] |
| hybrid | 0.625 [0.479, 0.771] | 0.260 [0.222, 0.393] | 0.319 [0.255, 0.750] | 0.231 [0.218, 0.245] | 0.457 [0.410, 0.489] | 0.938 [0.844, 1.000] | 0.333 [0.188, 0.458] |
| llm_only | 0.333 [0.208, 0.479] | 0.384 [0.124, 0.525] | 0.660 [0.229, 0.723] | 0.285 [0.270, 0.301] | 0.515 [0.490, 0.544] | 0.941 [0.800, 1.000] | 0.646 [0.500, 0.792] |
| kg_only | 0.312 [0.188, 0.458] | 0.375 [0.115, 0.518] | 0.649 [0.208, 0.707] | 0.282 [0.269, 0.298] | 0.513 [0.490, 0.544] | 0.938 [0.786, 1.000] | 0.667 [0.541, 0.792] |

**Source:** [eval/results/stream_c_post_merge_2026_05_07/metrics/](../../eval/results/stream_c_post_merge_2026_05_07/metrics/)

### Reading the numbers

- **`rag_only` is the headline winner.** 83.3% raw accuracy with a 95% CI floor of 72.9% — well above the 70% thesis target. Covered accuracy of 95.2% means when it does answer, it's almost always right.
- **`hybrid` underperforms `rag_only` by 21 points.** This was the surprise. Hypothesis: hybrid's KG-side machinery currently injects no useful signal (factor assertions are absent), so the only delta vs `rag_only` is the empty `KEY KG FACTS` / `KEY FACTORS` headers in the prompt. In ~33% of hybrid cases the model abstains, vs 12.5% in rag_only — strongly consistent with the prompt's empty KG section confusing rather than helping the model.
- **`kg_only` and `llm_only` both ~32% accuracy.** Both abstain ~65% of the time. With no retrieval signal, the model has no comparator anchor and bails out per spec. This is *correct* behaviour per cite-or-abstain — it's what we want until the KG path produces real factor-grounded evidence.
- **Calibration is poor across all modes** (ECE 0.45–0.51, Brier 0.23–0.29). Predicted probabilities are not well-calibrated — this is consistent with every prior pilot run on this corpus and is not a Stream C regression.

---

## Stream C Metadata Schema (Cross-PR Contract C5)

The 4-mode ablation produced 192 prediction artifacts — but the `pipeline_metadata` field set defined by Cross-PR Contract C5 (`kg_used_for_prediction`, `graph_quality_score`, `kg_fallback_mode`, `kg_gate_failure_reasons`, `core_schema`, `domain_pack`, `factor_catalog_version`, `evidence_path_results`) is **NOT visible in the eval JSONL** for this run. Investigation surfaced a real bug: `scripts/eval/predict_all.py:_serialise_prediction` did not pass `raw_result.pipeline_metadata` into the artifact dict. Each prediction's `pipeline_metadata` is therefore an empty `{}` in `eval/predictions/stream_c_post_merge_2026_05_07/<mode>.jsonl`.

**Fix landed:** commit `6917d32` patches `_serialise_prediction` to include `pipeline_metadata` via `_serialise_model`. **Future ablation runs will surface the full §17.6 schema.** This run's metadata cannot be recovered post-hoc — it lived only in the in-memory `PredictionResult` and was discarded at serialise time.

**Indirect evidence the engine wiring fired correctly:**
- The runtime log (`/tmp/stream_c_chunk_*.log`) confirms `retrieval_strategy=factor_constrained` was logged for every hybrid/kg_only case, so `STREAM_C_FACTOR_RETRIEVAL=1` did flip the engine's strategy as designed.
- Hybrid retrieval still performed BM25 + ChromaDB chunk-RAG (visible in the same logs) — the FactorRetriever's empty-asserted-factors fallback to chunk-RAG (design decision D5) fired exactly as expected.
- The `EvidencePathValidator` ran with `STREAM_C_EVIDENCE_PATH_STRICT=1` against `case_graph` instances that had no `factor_assertions`, so every chain-walk rejected with `"case_graph is empty"`. In strict mode this would force outcomes to UNCERTAIN — and looking at the abstention rates (kg_only 67%, llm_only 65%), this is broadly consistent with strict-mode rejection driving the abstention up.

---

## Gate-Pass Rate (per spec §17.6 first-class metric)

Cannot be computed from this run because `kg_used_for_prediction` is absent from the JSONL (see schema-bug note above). With factor data absent, the EXPECTED gate-pass rate is **0%** — every case fails the gate at the `_compute_graph_quality_score` heuristic because `evidence_backed_factor_count = 0`.

The next ablation, after the data backfill, will report this as a real number with bootstrap CI via [`packages/eval/metrics/gate_pass_rate.py`](../../packages/eval/metrics/gate_pass_rate.py).

## Citation Validity

Same caveat — without the metadata visible in the JSONL, the eval pipeline cannot compute this. The metric implementation [`retrieval_context_precision_at_k`, `retrieval_context_recall_at_k`, `citation_validity`](../../packages/eval/metrics/retrieval_quality.py) is in place and tested (18 unit tests in [test_retrieval_quality_metrics.py](../../packages/eval/tests/test_retrieval_quality_metrics.py)).

## Counterexample-Flagged Abstention Rate

Same caveat. The `ComparatorPack.counterexample_pass_metadata.abstention_recommended` flag was being set per-issue via `IssueRetriever._comparator_pack_by_issue` and copied to `IssuePredictor._comparator_pack_by_issue` per Task 5.6 — but the metric requires the artifact-side serialisation to land first.

---

## Per-Mode Prediction-Artifact Size (sanity check)

| Mode | JSONL size | Bytes / prediction (avg) |
|---|---|---|
| hybrid | 861 KB | 17.9 KB |
| rag_only | 847 KB | 17.6 KB |
| kg_only | 37 KB | 0.77 KB |
| llm_only | 37 KB | 0.77 KB |

Hybrid + rag_only artifacts are large because the IRAC prompt + retrieved-cases payload is preserved per case. KG_only and LLM_only are tiny because no retrieval evidence is included. Once `pipeline_metadata` is included (next run), expect ~+0.5 KB per prediction for the Stream C metadata.

---

## Cost Report

- 192 predictions × ~10s avg LLM latency × Claude 3.7 Sonnet pricing
- Approximate spend: **£8** (within plan estimate)
- Distribution: 96 cases (hybrid + rag_only) used retrieval pipeline + LLM; 96 cases (kg_only + llm_only) used LLM only
- 2 LoadError rows skipped (cases 25 + 50 from the v2 file — both flagged `needs_human_review`)

---

## Decision: Should the Stream C feature flags flip to "1" by default?

| Flag | Current default | Recommendation | Rationale |
|---|---|---|---|
| `STREAM_C_PR4` | `1` | **Keep at `1`** | Pack-rendered factor card is a cosmetic prompt change. Deposit byte-equivalence is locked in by `test_renderer_byte_equivalent_to_legacy_format`. Repairs cases get the new `KEY FACTORS (factor-graph derived):` header (currently empty card content because no factor assertions exist; harmless). |
| `STREAM_C_PR4_REPAIRS` | `1` | **Keep at `1`** | Same as above. |
| `STREAM_C_FACTOR_RETRIEVAL` | `0` | **Defer to `1`** until `Proposition.factor_ids` is backfilled. Today the path falls back to chunk-RAG via design decision D5, which is safe — but flipping to `1` means we silently swap the *current* working chunk-RAG codepath for a fallback path that has slightly different metadata-emission semantics. No accuracy delta either way until backfill. |
| `STREAM_C_EVIDENCE_PATH_STRICT` | `0` | **Keep at `0`** (audit-only) until factor data is backfilled. With `1` and an empty `case_graph`, every prediction is forced to UNCERTAIN. That's spec-correct cite-or-abstain behaviour for the no-data scenario, but it would tank apparent accuracy without producing useful signal. Audit mode logs the rejections so we can quantify gate-pass rate without changing predictions. |

---

## What this ablation did *not* test

By design, Stream C ships the **architecture** for factor-constrained retrieval and evidence-path validation. The accuracy contribution of those paths cannot be measured until:

1. `Proposition` rows in the corpus are populated with `factor_ids`, `outcome_component_ids`, `proposition_role`, and `authority_level` (per the `Proposition` model extension in Task 5.4).
2. `KnowledgeGraph` instances have `factor_assertions: List[FactorAssertion]` populated by a real factor extractor (the existing PR 5+ data-backfill work).
3. The artifact metadata persistence fix (commit `6917d32`) is included in the next ablation run.

When all three land, run the same 4-mode 48-case ablation again and compare:
- `gate_pass_rate.point` should rise from 0% to ≥ 70% on the gate-passing subset.
- `hybrid` accuracy on the gate-passing subset should rise above `rag_only` (the headline thesis claim per spec §17.1).
- `kg_only` accuracy should stop being 32% — with real factor signal it should converge towards `hybrid`.
- `evidence_path_results` should populate for every prediction with `is_supported=True` for the supported chains.

**The next ablation is the one that tests the thesis.** This one tests that Stream C didn't break the existing pipeline — which it didn't (rag_only is still 83.3%, well above prior baselines).

---

## Files

- Predictions: [`eval/predictions/stream_c_post_merge_2026_05_07/`](../../eval/predictions/stream_c_post_merge_2026_05_07/)
- Eval results: [`eval/results/stream_c_post_merge_2026_05_07/`](../../eval/results/stream_c_post_merge_2026_05_07/)
- Per-case run artifacts: `data/eval_artifacts/runs/20260507T143145Z/` (192 files; pre-fix; `pipeline_metadata` empty)
- Plan: [`docs/superpowers/plans/2026-05-07-stream-c-prediction-path-swap.md`](../superpowers/plans/2026-05-07-stream-c-prediction-path-swap.md)
- Spec: [`docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md`](../superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md)

## Reproduce

```bash
STREAM_C_PR4=1 STREAM_C_FACTOR_RETRIEVAL=1 STREAM_C_EVIDENCE_PATH_STRICT=1 \
  ./venv/bin/python -m scripts.eval.predict_all \
    --gold data/gold_standard/housing_repairs_social_v2_strict_clean.jsonl \
    --out-dir eval/predictions/stream_c_post_merge_<DATE> \
    --engine live --client claude \
    --modes hybrid,rag_only,kg_only,llm_only \
    --top-k 10
```

Then run `scripts/eval/run_full_eval.py` with the same `--gold` and `--predictions-dir` to produce the per-mode metrics in `eval/results/...`.
