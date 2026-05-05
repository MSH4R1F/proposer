# Housing Ombudsman Hybrid Debug Log

Date: 2026-05-05
Status: diagnostic log for the 50-case Housing Ombudsman live eval follow-up.

This log records why the retrieval-backed `hybrid` mode underperformed on the
first fixed 50-case live eval, what was changed, and what evidence exists after
the patch. The full 50-case live eval was rerun on 2026-05-05; those results
are now the current post-fix diagnostic baseline.

## Trigger

The fixed live run at
`eval/results/housing_ombudsman_stratified_50_live_20260504_202405_fixed_ordered_full_eval/`
scored as follows:

| Mode | Accuracy | Brier | ECE | Amount@20% |
| --- | ---: | ---: | ---: | ---: |
| `hybrid` | 0.420 | 0.238 | 0.464 | 0.500 |
| `rag_only` | 0.540 | 0.229 | 0.456 | 0.560 |
| `kg_only` | 0.680 | 0.323 | 0.550 | 0.640 |
| `llm_only` | 0.680 | 0.323 | 0.550 | 0.600 |

The surprising result was not just that `hybrid` failed to beat the ablations.
It was also worse than `rag_only`, despite being the mode that should combine
retrieval evidence and structured facts.

## Failure Pattern

The gold set is extremely tenant-heavy:

| Gold label | Count |
| --- | ---: |
| `tenant` | 49 |
| `landlord` | 1 |
| `split` | 0 |

The fixed live `hybrid` predictions were:

| Predicted label | Count |
| --- | ---: |
| `tenant` | 21 |
| `split` | 28 |
| `landlord` | 1 |

That means the main failure was over-predicting `split` or `uncertain`, not a
general inability to identify repairs issues. The wrong `hybrid` cases were
mostly tenant-win gold rows that were scored as `split`; the only landlord-win
gold row was also predicted as `split`.

Citation verification was not the primary explanation. Several wrong rows had
verified citations, so the model was often citing real determinations but then
mapping partial Ombudsman findings too conservatively.

## Root Causes

1. Live `hybrid` was not actually receiving a knowledge graph.

   `scripts/eval/predict_all.py` called `engine.predict(...)` without passing a
   `knowledge_graph`, even for `PredictionMode.HYBRID`. That made the live
   hybrid path behave like retrieval plus LLM prompting, not true RAG + KG.

2. Domain data was stuck in metadata instead of top-level `CaseFile` fields.

   The gold rows carried `domain_id`, `domain_version`, and Ombudsman matter
   types in metadata, but the reconstructed `CaseFile` still defaulted toward
   the deposit-dispute domain. That weakened domain-specific routing,
   retrieval, and prompt behavior.

3. Retrieval issue expansion was still deposit-shaped.

   The reranker keyword map did not contain repairs, damp, mould, disrepair, or
   complaint-handling vocabulary. In debug logs, this showed up as empty
   `query_issues=[]` for repairs cases. The candidate pool was also too narrow
   for the Ombudsman corpus, where relevant remedy and outcome language is often
   separate from the first issue-summary chunks.

4. Ombudsman outcome semantics were mapped too conservatively.

   The shared outcome parser and prompt language treated partial findings,
   mixed findings, and some reasonable-redress style determinations as `split`.
   For this eval, a case should usually score as `tenant_wins` when any
   substantive repairs or complaint-handling issue is upheld, or when the
   resident receives an additional remedy, even if not every complaint head is
   upheld.

5. Retrieval metadata remains thinner than the Phase 4 verifier contract.

   `RetrievalResult` and `Citation` still lose some source metadata that would
   help explain verification failures and compare citation spans more precisely.
   This was not the main accuracy driver in this run, but it is still a product
   evidence risk.

6. The 50-case gold set is skewed.

   With 49 tenant rows and 1 landlord row, plain accuracy mostly rewards models
   that predict tenant. This is acceptable for a pilot set, but not enough for a
   final thesis or product-evidence claim. Macro-F1, confusion tables, and a
   better no-maladministration or landlord-reasonable-action stratum are needed.

## Fixes Made

The follow-up patch changed these areas:

| Area | Files |
| --- | --- |
| Pass KG into live eval for `hybrid` and `kg_only` | `scripts/eval/predict_all.py` |
| Preserve top-level domain and matter metadata on reconstructed cases | `packages/eval/case_file_adapter.py` |
| Add repairs/Ombudsman issue terms to retrieval config | `packages/rag_engine/config.py` |
| Widen and rerank repairs retrieval candidates with issue and outcome signals | `packages/llm_orchestrator/pipeline/issue_retrieval.py` |
| Align repairs prompt and outcome normalization with Ombudsman eval semantics | `packages/llm_orchestrator/pipeline/issue_predictor.py` |
| Align the Housing Ombudsman prompt pack with the same semantics | `packages/llm_orchestrator/prompts/packs/housing_repairs_social_v1.py` |
| Add regression coverage for the wiring and mapping behavior | `packages/eval/tests/`, `packages/llm_orchestrator/tests/`, `packages/rag_engine/tests/` |

Key behavior changes:

- `hybrid` and `kg_only` now build a repairs-domain knowledge graph before live
  prediction.
- Ombudsman `partial_upheld`, `partly_upheld`, and
  `partial_maladministration` normalize to `tenant_wins` for this eval target.
- Repairs retrieval gets a larger candidate pool and reranks toward issue
  matches plus outcome/remedy-bearing chunks.
- Repairs queries now start from case-specific issue terms and facts instead of
  generic Housing Ombudsman wording.

## Evidence After Patch

Regression tests:

```bash
PYTHONPATH=packages venv/bin/pytest \
  packages/eval/tests/test_case_file_adapter.py \
  packages/llm_orchestrator/tests/test_issue_predictor.py \
  packages/eval/tests/test_predict_all.py \
  packages/eval/tests/test_adapter.py \
  packages/rag_engine/tests/test_bm25_metadata_filters.py \
  packages/rag_engine/tests/test_reranker.py \
  packages/llm_orchestrator/tests/test_issue_retrieval_kg_filter.py \
  packages/llm_orchestrator/tests/test_openai_client.py \
  -q
```

Result: `120 passed in 1.44s`.

Live smoke command:

```bash
PYTHONPATH=packages venv/bin/python scripts/eval/predict_all.py \
  --gold data/gold_standard/housing_repairs_social_v1.jsonl \
  --out-dir eval/predictions/housing_ombudsman_hybrid_debug_smoke_20260505_004047 \
  --engine live \
  --client openai \
  --modes hybrid \
  --limit 5 \
  --rag-index-root indices \
  --top-k 5 \
  --run-id housing_ombudsman_hybrid_debug_smoke_20260505_004047
```

Smoke result:

| Case | Gold | Old fixed live `hybrid` | New patched smoke `hybrid` |
| --- | --- | --- | --- |
| `202451564` | tenant | tenant | tenant |
| `202427949` | tenant | split/uncertain | tenant |
| `202332678` | tenant | split/uncertain | tenant |
| `202426484` | tenant | tenant | tenant |
| `202409223` | tenant | tenant | tenant |

The first five cases improved from `3/5` to `5/5`. The two previous misses,
`202427949` and `202332678`, flipped from `split/uncertain` to `tenant_win`
with verified citations. Two of the five smoke rows still had citation
verification failures and confidence caps, so citation metadata remains a real
follow-up item.

## Full Post-Fix Rerun

Artifacts:

- `eval/predictions/housing_ombudsman_stratified_50_live_20260505_005603_hybrid_fix/`
- `eval/results/housing_ombudsman_stratified_50_live_20260505_005603_hybrid_fix_full_eval/audit.json`
- `eval/results/housing_ombudsman_stratified_50_live_20260505_005603_hybrid_fix_full_eval/ablation.json`
- `eval/results/housing_ombudsman_stratified_50_live_20260505_005603_hybrid_fix_full_eval/summary.json`

Run method:

- `kg_only` and `llm_only` were run as one live 50-case process each.
- `hybrid` and `rag_only` were run as five 10-case retrieval shards against
  the local 1,000-case Housing Ombudsman index with
  `--rag-index-root indices --top-k 5`.
- Retrieval shards were merged back into gold order before scoring.
- Scoring used `seed=42`, `n_resamples=1000`, `min_case_count=50`, and
  `domain=housing.repairs_social.v1`.

Results, n=50:

| Mode | Accuracy | Accuracy 95% CI | Brier | Brier 95% CI | ECE | Amount@20% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `hybrid` | 0.800 | [0.680, 0.900] | 0.228 | [0.205, 0.252] | 0.449 | 0.480 |
| `rag_only` | 0.780 | [0.680, 0.900] | 0.205 | [0.182, 0.228] | 0.423 | 0.500 |
| `kg_only` | 1.000 | [1.000, 1.000] | 0.360 | [0.360, 0.360] | 0.600 | 0.560 |
| `llm_only` | 0.980 | [0.920, 1.000] | 0.356 | [0.344, 0.360] | 0.580 | 0.700 |

Prediction distribution:

| Mode | Tenant | Landlord | Split | Raw abstentions |
| --- | ---: | ---: | ---: | ---: |
| `hybrid` | 40 | 1 | 9 | 9 |
| `rag_only` | 39 | 1 | 10 | 10 |
| `kg_only` | 49 | 1 | 0 | 0 |
| `llm_only` | 48 | 2 | 0 | 0 |

Confusion summary:

- Gold distribution remains heavily skewed: `tenant=49`, `landlord=1`.
- `hybrid` gets `40/50` right: 40 tenant wins. Its misses are 8 tenant rows
  collapsed from raw `uncertain` to eval `split`, 1 tenant row predicted
  `landlord`, and the single landlord row collapsed to `split`.
- `rag_only` gets `39/50` right: 39 tenant wins. Its misses are 9 tenant rows
  collapsed from raw `uncertain` to `split`, 1 tenant row predicted
  `landlord`, and the single landlord row collapsed to `split`.
- `kg_only` gets `50/50` right and `llm_only` gets `49/50` right, but this is
  not strong evidence that no-RAG is product-superior because the pilot gold set
  is almost all tenant-favorable.

## Current Interpretation

The old `hybrid=0.420` number is deprecated. It measured a retrieval-backed
path with broken KG wiring, deposit-shaped retrieval expansion, and overly
conservative Ombudsman outcome mapping. After the fixes, `hybrid` improved from
`21/50` to `40/50`, and `rag_only` improved from `27/50` to `39/50`.

The fix is real, but the result is still diagnostic rather than final thesis
evidence. The no-RAG modes score extremely high because the set is
tenant-heavy, while the retrieval-backed modes still abstain on hard cases
after citation verification. Calibration also remains weak: all ECE values are
high, and only `rag_only` is close to the target Brier threshold of `<0.20`.

## Reproduction Command

Use the local 1,000-case Housing Ombudsman index and keep the explicit
`--rag-index-root indices` flag so the eval does not accidentally hit the small
or stale `data/indices` pilot path:

```bash
PYTHONPATH=packages venv/bin/python scripts/eval/predict_all.py \
  --gold data/gold_standard/housing_repairs_social_v1.jsonl \
  --out-dir eval/predictions/housing_ombudsman_stratified_50_live_20260505_005603_hybrid_fix \
  --engine live \
  --client openai \
  --modes hybrid,rag_only,kg_only,llm_only \
  --rag-index-root indices \
  --top-k 5 \
  --run-id housing-ombudsman-stratified-50-live-20260505-005603-hybrid-fix
```

Then score it:

```bash
PYTHONPATH=packages venv/bin/python scripts/eval/run_full_eval.py \
  --gold data/gold_standard/housing_repairs_social_v1.jsonl \
  --predictions-dir eval/predictions/housing_ombudsman_stratified_50_live_20260505_005603_hybrid_fix \
  --out-dir eval/results/housing_ombudsman_stratified_50_live_20260505_005603_hybrid_fix_full_eval \
  --domain housing.repairs_social.v1 \
  --seed 42 \
  --n-resamples 1000 \
  --min-case-count 50
```

## Remaining Work

- Do not treat the 50-case pilot as final thesis evidence until the eval set is
  less tenant-skewed.
- Add confusion matrices and macro-F1 to the standard eval report.
- Keep `uncertain` as a first-class abstention diagnostic instead of only
  collapsing it into the three-class winner enum.
- Carry Phase 4 source metadata through retrieval and citation artifacts.
- Expand the repairs KG with report dates, vulnerability, landlord delay,
  outstanding works, complaint-stage delays, and prior offers.
- Add more no-maladministration, reasonable-redress, and landlord-favorable
  cases to reduce pilot-set skew.

## 2026-05-05 KG-Only / Amount Leakage Audit

Follow-up audit after `kg_only=1.000` found that the no-RAG modes were not
secretly using RAG or reading `ground_truth_outcome`. The number was inflated
by two eval-design problems:

- The 50-case gold set is `49` tenant wins and `1` landlord win, so an
  always-tenant baseline scores `0.980`.
- The legacy Ombudsman gold promotion path copied final compensation/order
  values into prediction-input fields: `disputed_amount_gbp` and
  `claimed_amounts`. A claim-copy deterministic baseline therefore scored
  perfect amount accuracy on the old artifacts.

Patch summary:

- Suppressed legacy outcome-derived Ombudsman amounts in
  `gold_case_to_case_file()`.
- Updated Ombudsman review prep so final compensation stays only in
  `ground_truth_outcome`.
- Allowed unknown pre-decision amount fields for `housing.repairs_social.v1`.
- Stopped the issue predictor from filling missing `predicted_amount` with
  `issue.claimed_amount`.
- Added deterministic baselines and richer amount metrics to full eval.
- Made claim-copy baselines ignore the same legacy outcome-derived Ombudsman
  amount fields that the prediction CaseFile adapter suppresses.
- Added a balanced outcome sampler for the next 50-case Ombudsman eval set.

Verification:

- `566` eval tests passed.
- `20` focused LLM orchestrator tests passed.
- Current promoted 50-row adapter smoke found `0` leaked award amounts.
- Full-eval smoke emitted baselines showing the outcome skew clearly:
  `always_tenant accuracy=0.980`. The old claim-copy amount leak is now
  suppressed in the baseline report:
  `claim_amount_copy amount@GBP100=0.000`, `amount_n=0`.

Do not report the old `kg_only=1.000` or amount metrics as product evidence.
Regenerate a balanced, reviewed gold set and rerun live predictions through the
patched adapter before using the numbers in SHA-68 or thesis material.
