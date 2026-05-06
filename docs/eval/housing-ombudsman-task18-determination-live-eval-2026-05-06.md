# Housing Ombudsman Task 18 Determination Live Eval - 2026-05-06

This records the post-ontology live evaluation run reported on 2026-05-06 after
the two main PRs were merged into `main`:

- PR #31: purposeful Housing Ombudsman retrieval / ablation hardening.
- PR #32: Housing Ombudsman determination ontology, split amount constructs,
  v2 gold migration, and determination-aware eval metrics.

The run is referred to below as **Task 18 / v2_valid48 / par40**.

## Executive Summary

The run is a major recovery from the earlier binary balanced-50 failure, but it
does **not** yet prove the hybrid system is product-ready.

- Runtime: 192 OpenAI calls launched as 40 parallel shards.
- Wall clock: about 13 minutes, from 16:11 to 16:21 BST.
- Estimated OpenAI spend: USD 10-15.
- Valid scored rows: 48.
- Hybrid has the best legacy binary accuracy: `0.833`.
- RAG-only has slightly higher covered accuracy: `0.951` vs hybrid `0.930`,
  because it abstained on two more borderline rows.
- The honest headline for Housing Ombudsman is determination accuracy, not
  legacy tenant/landlord accuracy. Hybrid is `0.542`; RAG-only is `0.500`.
- Hybrid still misses the minority determination classes: zero recall on
  `reasonable_redress`, `severe_maladministration`, and
  `resolved_with_intervention`.

The key conclusion is methodological: **legacy binary accuracy is inflated by
the corpus skew**. On this run, the always-tenant baseline is `0.979`; on the
earlier balanced-50 binary run it was `0.500`. Report `determination.accuracy`
and per-class recall as the primary Housing Ombudsman outcome metrics.

## Artifacts

Reported run artifacts:

- Predictions: `eval/predictions/task18_par40_20260506_161134/{hybrid,rag_only,kg_only,llm_only}.jsonl`
- Per-shard outputs: `eval/predictions/task18_par40_20260506_161134/shard*_<mode>/`
- Logs: `eval/predictions/task18_par40_20260506_161134/logs/shard*_<mode>.log`
- Eval summary: `eval/results/task18_par40_20260506_161134_full_eval/{summary.json,ablation.json,audit.json,metrics/}`

Note: these generated artifact directories are not present in the pulled
checkout at the time this document was written. The numbers below are recorded
from the reported run output.

## Headline Metrics

`accuracy` and `covered_accuracy` are the legacy winner-axis metrics.
`determination.accuracy` is the seven-class Housing Ombudsman metric and should
be the headline.

| Mode | Legacy accuracy | Covered accuracy | Abstention | Non-abstained | Correct covered | Determination accuracy | Within 20% | Within GBP100 | MAE ordered_now | Legacy amount MAE | Amount n |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `hybrid` | 0.833 | 0.930 | 0.104 | 43 | 40 | 0.542 | 0.083 | 0.104 | GBP 504 | GBP 568 | 37 |
| `rag_only` | 0.812 | 0.951 | 0.146 | 41 | 39 | 0.500 | 0.104 | 0.125 | GBP 487 | GBP 534 | 35 |
| `kg_only` | 0.333 | 0.941 | 0.646 | 17 | 16 | 0.146 | 0.000 | 0.000 | GBP 668 | n/a | 0 |
| `llm_only` | 0.167 | 1.000 | 0.833 | 8 | 8 | 0.146 | 0.000 | 0.000 | GBP 668 | n/a | 0 |

Two amount columns are intentionally kept separate:

- `MAE ordered_now` is the construct-specific mean absolute error for fresh
  Ombudsman compensation orders. It counts missing predictions as full-magnitude
  errors when the gold ordered-now amount is positive.
- `Legacy amount MAE` is the backward-compatible `amount.mae_gbp` summary field.
  It only uses evaluable gold/prediction amount pairs. When `Amount n = 0`, it
  is not evidence even if older JSON renderers print `0.0`.

## Covered Accuracy Math

RAG-only's covered accuracy is higher because covered accuracy excludes
abstentions from the denominator.

| Mode | Predicted on | Correct | Covered accuracy |
|---|---:|---:|---:|
| `hybrid` | 43/48 | 40 | 40/43 = 0.930 |
| `rag_only` | 41/48 | 39 | 39/41 = 0.951 |
| `kg_only` | 17/48 | 16 | 16/17 = 0.941 |
| `llm_only` | 8/48 | 8 | 8/8 = 1.000 |

This is the normal precision-via-abstention pattern. A model can look excellent
on the cases it answers while being too quiet for product use. Compare modes on
legacy `accuracy`, `coverage_adjusted_accuracy`, and, for Housing Ombudsman,
`determination.accuracy` plus per-class recall.

## Determination Recall

Hybrid per-class recall:

| Gold determination | Recall | Correct / total |
|---|---:|---:|
| `maladministration` | 0.77 | 24/31 |
| `outside_jurisdiction` | 1.00 | 1/1 |
| `service_failure` | 0.14 | 1/7 |
| `reasonable_redress` | 0.00 | 0/4 |
| `severe_maladministration` | 0.00 | 0/3 |
| `resolved_with_intervention` | 0.00 | 0/2 |

This is the same tenant-bias / majority-class pattern flagged in the RCA, but
now visible on the right ontology. The model is strong on the dominant
`maladministration` class and weak to nonexistent on the smaller classes.

## What Changed So Far

### PR #31 - purposeful retrieval / ablation hardening

Merge commit: `26ace0f`.

Key implementation surface:

- `packages/llm_orchestrator/pipeline/issue_retrieval.py`
- `packages/llm_orchestrator/pipeline/issue_predictor.py`
- `packages/llm_orchestrator/pipeline/prediction_engine_v2.py`
- `packages/llm_orchestrator/tests/test_prediction_modes.py`

Purpose:

- Harden Housing Ombudsman ablation modes.
- Improve purposeful retrieval and KG-aware filtering.
- Make retrieval-backed modes less dependent on generic tenant-favouring chunks.

### PR #32 - determination ontology and amount constructs

Merge commit: `d679130`.

Key implementation surface:

- `packages/eval/schema.py`
- `packages/eval/metrics/accuracy.py`
- `packages/eval/compare.py`
- `packages/eval/adapter.py`
- `packages/llm_orchestrator/models/prediction_v2.py`
- `packages/llm_orchestrator/pipeline/output_assembler.py`
- `packages/llm_orchestrator/prompts/packs/housing_repairs_social_v1.py`
- `scripts/eval/migrate_balanced50_to_determination_schema.py`
- `data/gold_standard/housing_repairs_social_v2.jsonl`
- `docs/eval/housing-ombudsman-determination-ontology-2026-05-06.md`

Purpose:

- Add the seven-class `Determination` ontology.
- Require `determination` on `housing.repairs_social.v1` rows.
- Split amount constructs into:
  `amount_ordered_now_gbp`, `amount_previously_offered_gbp`, and
  `amount_global_unapportioned_gbp`.
- Carry `predicted_determination` and `amount_construct` through prediction and
  eval adapters.
- Emit `determination.accuracy`, per-class recall, and per-construct amount MAE.
- Emit `null` for deposit-style baselines on housing gold instead of misleading
  `0.0` accuracy.

### Follow-up PR #33 - serialization and prompt strengthening

Branch: `followup/strengthen-housing-determination-prompt`.

Reported commits:

- `b03787e` - housing user prompt explicitly requires the new fields.
- `62e1d47` - `predict_all._serialise_prediction` writes the new fields to JSONL.
- `800abbc` - `eval.run._dict_to_prediction` reads the new fields back.
- Plus a `run_full_eval._summarise_eval_row` guard for `null` baseline accuracy
  from Task 8's deposit-baseline guard.

At the time this note was written, these follow-up commits were reported as
ready on PR #33; they are not part of the pulled `main` history shown by
`git log --oneline` (`HEAD=d679130`).

## Interpretation

The run answers a different question than the earlier balanced-50 binary eval.
It shows that the new ontology lets us see what was previously hidden:

- Binary tenant/landlord accuracy can be high for the wrong reason when the gold
  set is heavily tenant-leaning.
- Hybrid is still the best legacy-accuracy mode, but its advantage is not yet
  thesis-grade because determination recall is concentrated in the dominant
  class.
- RAG-only's higher covered accuracy is not a contradiction; it abstained on a
  slightly harder subset.
- KG-only and LLM-only are still dominated by abstention. Their covered accuracy
  is diagnostic, not product evidence.
- The amount model remains weak. Within GBP100 is only `0.104` for hybrid and
  `0.125` for RAG-only; within 20% is `0.083` and `0.104`.

## Next Steps

1. Make determination metrics the Housing Ombudsman gate.
   - Primary: `determination.accuracy`, macro recall / balanced recall, and
     per-class recall.
   - Secondary: legacy binary accuracy for backward compatibility only.

2. Build a minority-class eval slice before another headline run.
   - Target enough `reasonable_redress`, `service_failure`,
     `severe_maladministration`, and `resolved_with_intervention` cases that a
     recall movement is meaningful.
   - Do not optimize against the v2_valid48 class skew alone.

3. Add class-aware failure packets.
   - For every zero-recall class, store the prompt, retrieved chunks, gold
     determination, predicted determination, and citation-verification outcome.
   - Use this to tell whether failures are prompt, retrieval, schema, or source
     ambiguity.

4. Improve retrieval for non-maladministration determinations.
   - Add determination-aware query templates.
   - Raise the weight of orders/determination chunks for amount prediction.
   - Track retrieval stance and determination class in top-k diagnostics.

5. Keep point amount predictions out of product.
   - Product-safe path is still bands or abstention.
   - Report `amount.within_gbp100` and construct-specific MAE together.
   - Do not quote legacy `amount.mae_gbp` when `Amount n` is low or zero.

6. Land PR #33, then rerun the same par40 recipe.
   - Same shard count, same seed, same 48-row valid set.
   - Confirm JSONL serialization preserves `predicted_determination` and
     `amount_construct`.
   - Promote the successor run only if minority recall improves without lowering
     citation validity.
