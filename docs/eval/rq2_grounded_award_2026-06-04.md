# RQ2 — Grounded Award Anchor Ablation (housing repairs, 2026-06-04)

Authoritative record for the RQ2 settlement-alignment result reported in
`Proposer-Final-Report/evaluation/evaluation.tex` (§`sec:eval-rq2`, `tab:eval-rq2`).
Supersedes the asserted/`llm_only`-only RQ2 result from 2026-06-02.

## Design

Four-arm ablation that **separates the always-predict policy from the
retrieval/KG capability**, so the causal comparison is fair. Corpus:
`data/gold_standard/housing_repairs_social_v2_strict_clean.jsonl` (n=48),
`gpt-5.5`, `scripts/eval/rq2_settlement_fairness.py`. Repairs is the only
non-deposit domain with a built retrieval index (`indices/housing_repairs_social_v1/`);
employment has no index and is out of scope (future work).

| Arm | mode | flags |
|---|---|---|
| `legacy_llm_only_strict` | llm_only | none |
| `llm_only_always_predict` | llm_only | `STREAM_C_NO_RAG_PREDICT_AMOUNTS=1` |
| `rag_only_always_predict` | rag_only | `STREAM_C_ALWAYS_PREDICT_AMOUNTS=1` |
| `hybrid_always_predict` | hybrid | `STREAM_C_ALWAYS_PREDICT_AMOUNTS=1` |

Baseline = leave-one-out median award. `Δ AE` = paired bootstrap (1000 resamples,
seed 42) of per-case absolute-error difference (baseline − settlement); +ve favours
the settlement; interval straddling zero ⇒ no significant difference.

## Results (n=48)

| Arm | ZOPA found | within ±20% | within £100 | MAE £ | actual-in-ZOPA | Δ AE vs base (£, 95% CI) |
|---|---|---|---|---|---|---|
| Median-award baseline | — | 25% | 31% | 437 | — | — (reference) |
| legacy (strict cite-or-abstain) | 0% | 4% | 13% | 704 | 0% | **−268 [−351, −168]** worse |
| llm_only_always_predict (free) | 92% | 15% | 19% | 482 | 10% | **−46 [−107, +18]** tied |
| rag_only_always_predict (comparator) | 92% | 15% | 29% | 498 | 10% | **−61 [−132, +13]** tied |
| hybrid_always_predict (RAG+KG) | 92% | 19% | 27% | 454 | 15% | **−17 [−76, +49]** tied |

## Findings

1. **Degeneracy fixed.** Always-predicting lifts the non-degenerate-ZOPA rate from 0% to 92% (the remaining ~8% are issues the model marks `uncertain`, whose amount the assembler drops by design).
2. **Parity, not victory.** All three always-predict arms move from *strictly worse* (legacy, CI entirely below 0) to *statistically tied* with the baseline (CIs straddle 0). None beats it.
3. **Retrieval grounding ≈ free estimate.** `rag_only` does not significantly beat `llm_only_always_predict`; it improves absolute closeness (within £100: 29% vs 19%) but not MAE/within-20%.
4. **KG was inert.** `kg_used_for_prediction` = false and graph-quality = 0 on all 48 hybrid cases, so `hybrid` ≈ `rag_only` + inert graph; its slightly better point estimate cannot be credited to the KG. Mirrors the RQ1 "control plane rarely fires" finding.
5. **Calibration poor.** The actual award lands inside the proposed ZOPA band on only 10–15% of cases.
6. **Conclusion.** The anchor is *necessary* (removes the collapse) but *not sufficient* (does not beat a naive median). Bottleneck = monetary-quantum estimation + retrieval quality, not the missing anchor.

## Integrity note

Cite-or-abstain is relaxed **for the settlement quantum only**; citations and
determinations remain strictly grounded. Per-case `amount_anchor_source`
(`comparator`/`free_estimate`) is derived from whether retrieved chunk previews
carried a £ figure — a retrieval-side coverage signal, not a claim about which
figure the model used. `source_id` is absent on this index's chunks, so
`amount_source_ids` is empty and the post-hoc `leakage_ok` cross-check is weak;
the actual leakage filter (`_EvalFilteredRAGPipeline` + `excluded_source_ids`)
runs at retrieval time and reported `leakage_ok_rate` 1.0.

## Reproduce

```bash
set -a && source .env && set +a
# legacy
PYTHONPATH=.:packages venv/bin/python scripts/eval/rq2_settlement_fairness.py \
  --gold data/gold_standard/housing_repairs_social_v2_strict_clean.jsonl \
  --mode llm_only --arm legacy_llm_only_strict --client default
# always-predict, no retrieval
STREAM_C_NO_RAG_PREDICT_AMOUNTS=1 PYTHONPATH=.:packages venv/bin/python scripts/eval/rq2_settlement_fairness.py \
  --gold data/gold_standard/housing_repairs_social_v2_strict_clean.jsonl \
  --mode llm_only --arm llm_only_always_predict --client default
# retrieval / hybrid (add STREAM_C_ALWAYS_PREDICT_AMOUNTS=1, --mode rag_only|hybrid, --rag-index-root indices)
```

Artifacts (summary.json + per_case.jsonl per arm): `data/eval_artifacts/runs/rq2_{arm}/`.
