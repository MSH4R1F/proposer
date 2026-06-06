# RQ2 — Agentic GraphRAG + the parity ceiling (housing repairs, 2026-06-05)

Final RQ2 state. Supersedes the framing in `rq2_grounded_award_2026-06-04.md` (the deposit-centric degeneracy is fixed; the question is now whether a grounded settlement beats the median baseline — it does not, significantly).

## The full ablation (repairs, n=48, gpt-5.5, baseline = leave-one-out median award)

| Arm | ZOPA found | within ±20% | MAE £ | Δ AE vs base (£, 95% CI) |
|---|---|---|---|---|
| Median-award baseline | — | 25% | 437 | — (reference) |
| Strict cite-or-abstain (legacy) | 0% | 4% | 704 | **−268 [−351, −168]** strictly worse |
| Always-predict, free estimate | 92% | 15% | 482 | −46 [−107, +18] tied |
| Always-predict, grounded (RAG, v2) | 92% | 25% | 464 | −27 [−95, +39] tied |
| Always-predict, grounded (RAG+KG, v2) | 94% | **27%** | 443 | **−6 [−59, +50]** parity, nominally ahead on ±20% |
| Agentic GraphRAG (tool-using) | 100% | 8% | 579 | **−142 [−229, −59]** significantly worse |

Artifacts: `data/eval_artifacts/runs/rq2_{hybrid,rag_only}_always_predict_v2/`, `rq2_agentic_graphrag_v1/`.

## The finding (the real result)

**Parity is the honest ceiling; per-case award magnitude is not recoverable from comparable decisions on these corpora.**

1. Grounding the always-predicted quantum in retrieved **ordered totals** (not incidental £ figures) + de-biasing + a comparator-anchored clamp lifts the single-pass mechanism from *strictly worse* to *parity*; the hybrid arm matches the baseline's MAE and **nominally** leads on within-±20% (27% vs 25%), but within noise (−£6 [−59,+50]).
2. A purpose-built **agentic GraphRAG** predictor (searches, reads comparator order amounts, emits a cited ZOPA) does **not** beat the baseline either. The decisive evidence is its **symmetric failure**: anchored on the lower raw figures it under-predicts (MAE 369 on a 12-case probe); anchored on the extracted order totals it over-predicts (MAE 490 probe / 579 full). Neither tracks the actual awards.
3. **Why:** the awards cluster tightly (median £500) with a heavy, idiosyncratic tail (to £3,818); retrieval surfaces comparator orders clustered at £20–£1,500. The leave-one-out median is therefore the MAE-minimising constant, and any per-case signal — in either direction — is essentially uncorrelated with the true award, so it *raises* error rather than lowering it.

## Integrity note
Beating the baseline on award-magnitude MAE was not achievable without gaming (overfitting the 48 cases, weakening the baseline, or leaking gold awards), so it was not attempted. The negative result is reported plainly, consistent with the project's cite-or-abstain ethos.

## Agentic predictor — where it lives
`RetrievalStrategy.AGENTIC_PREDICT` under `mode=hybrid`; `packages/llm_orchestrator/pipeline/agentic_predictor.py` (tools `search_cases`/`read_amounts`/`list_case_factors`/`finalize_prediction`, self-contained loop). Engine branch `PredictionEngineV2._agentic_predict`; harness `--mode agentic`. Reproduce:

```bash
set -a && source .env && set +a
export STREAM_C_KG_GATE_RELAXED=1 STREAM_C_PROPOSITION_TAG_FUZZY=1 STREAM_C_PR4=1 STREAM_C_EVIDENCE_PATH_STRICT=0
unset STREAM_C_FACTOR_RETRIEVAL STREAM_C_ALWAYS_PREDICT_AMOUNTS
PYTHONPATH=.:packages venv/bin/python scripts/eval/rq2_settlement_fairness.py \
  --gold data/gold_standard/housing_repairs_social_v2_strict_clean.jsonl \
  --mode agentic --arm agentic_graphrag_v1 --client default --rag-index-root indices \
  --out-dir data/eval_artifacts/runs/rq2_agentic_graphrag_v1
```
