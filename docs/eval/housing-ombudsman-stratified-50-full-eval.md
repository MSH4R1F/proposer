# Housing Ombudsman Stratified 50 Full Eval Run

This records the 2026-05-04 accuracy/Brier/ECE/ablation run over the
reviewed 50-case Housing Ombudsman repairs/social gold corpus.

Artifacts:

- `scripts/eval/promote_housing_ombudsman_reviewed_gold.py`
- `data/gold_standard/housing_repairs_social_v1.jsonl`
- `data/eval_artifacts/gold_build/housing-ombudsman-stratified-50-review-20260504-reviewed/promotion_summary.json`
- `eval/predictions/housing_ombudsman_stratified_50_20260504/`
- `eval/results/housing_ombudsman_stratified_50_full_eval_20260504/audit.json`
- `eval/results/housing_ombudsman_stratified_50_full_eval_20260504/ablation.json`
- `eval/results/housing_ombudsman_stratified_50_full_eval_20260504/summary.json`

Promotion command:

```bash
PYTHONPATH=packages venv/bin/python scripts/eval/promote_housing_ombudsman_reviewed_gold.py \
  --promote-canonical \
  --force
```

Prediction command:

```bash
PYTHONPATH=packages venv/bin/python scripts/eval/predict_all.py \
  --gold data/gold_standard/housing_repairs_social_v1.jsonl \
  --out-dir eval/predictions/housing_ombudsman_stratified_50_20260504 \
  --engine stub \
  --modes hybrid,rag_only,kg_only,llm_only \
  --run-id housing-ombudsman-stratified-50-stub-20260504
```

Eval command:

```bash
PYTHONPATH=packages venv/bin/python scripts/eval/run_full_eval.py \
  --gold data/gold_standard/housing_repairs_social_v1.jsonl \
  --predictions-dir eval/predictions/housing_ombudsman_stratified_50_20260504 \
  --out-dir eval/results/housing_ombudsman_stratified_50_full_eval_20260504 \
  --domain housing.repairs_social.v1 \
  --seed 42 \
  --n-resamples 1000 \
  --min-case-count 50
```

Results, n=50:

| Mode | Accuracy | Accuracy 95% CI | Brier | Brier 95% CI | ECE | ECE 95% CI | Amount@20% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| hybrid | 0.360 | [0.220, 0.500] | 0.345 | [0.255, 0.429] | 0.497 | [0.408, 0.581] | 1.000 |
| rag_only | 0.340 | [0.220, 0.460] | 0.284 | [0.234, 0.336] | 0.472 | [0.405, 0.536] | 1.000 |
| kg_only | 0.380 | [0.260, 0.520] | 0.261 | [0.225, 0.294] | 0.482 | [0.432, 0.526] | 1.000 |
| llm_only | 0.340 | [0.220, 0.480] | 0.254 | [0.242, 0.266] | 0.484 | [0.440, 0.513] | 1.000 |

Interpretation:

- This is the first scoreable 50-case Ombudsman gold run: all 50 rows passed
  the real-gold append gate with `LabelingProvenance`, mandatory human-review
  provenance, target source IDs, and no leakage violations.
- These numbers are a baseline harness result only. The prediction command used
  `--engine stub`, so this does not measure the live hybrid RAG/KG product.
- Hybrid does not dominate on this baseline. `kg_only` has the highest point
  accuracy, `llm_only` has the lowest Brier point estimate, and all accuracy CIs
  overlap heavily.
- The Brier target `<0.20` does not land for any mode on this run.
- `Amount@20% = 1.000` should not be used as settlement-amount evidence because
  the prediction artifacts are deterministic stub outputs, not independent live
  predictions.

Audit notes:

- `n_cases=50`, `test_count=50`, `train_count=0`.
- Leakage violations: none.
- `is_clean=false` because the generic deposit-domain audit still checks
  deposit claim-type strata (`cleaning`, `damages`, `deposit_non_protection`,
  `end_of_tenancy`). That is expected for `housing.repairs_social.v1`.
- Region distribution is `london=48`, `west_midlands=2`; this reflects the
  deterministic region fallback in the draft review pipeline and is not yet
  reliable regional evidence.
- `predict_all.py` warned that `disrepair` is unmappable into the older
  deposit-dispute `DisputeIssue` enum. Per-issue metrics are therefore not
  meaningful until the Ombudsman issue vocabulary is wired through.

Live prediction wiring:

The live runner now supports the Housing Ombudsman Chroma/BM25 namespace,
target-source exclusion, source/forum/matter filters, and repairs-specific
`disrepair` issue mapping. To generate product-evidence candidate predictions
against the local full 1,000-case index:

```bash
PYTHONPATH=packages venv/bin/python scripts/eval/predict_all.py \
  --gold data/gold_standard/housing_repairs_social_v1.jsonl \
  --out-dir eval/predictions/housing_ombudsman_stratified_50_live_$(date +%Y%m%d) \
  --engine live \
  --client openai \
  --modes hybrid,rag_only,kg_only,llm_only \
  --rag-index-root indices \
  --top-k 5 \
  --run-id housing-ombudsman-stratified-50-live-$(date +%Y%m%d)
```

Use `--client claude` to run the Anthropic path. The command requires provider
API keys for both prediction and retrieval embeddings. If the canonical index is
under `data/indices/` instead of `indices/`, omit `--rag-index-root` or pass
`--rag-index-root data/indices`.

Live diagnostic note, 2026-05-04:

A clean live run completed under
`eval/results/housing_ombudsman_stratified_50_live_20260504_191650_sharded2_topk5_ordered_full_eval/`
with `hybrid=0.420` and `rag_only=0.340` point accuracy, but it must not be
reported as product evidence. The `kg_only` and `llm_only` rows scored `0.000`
because their raw orchestrator outputs were all `uncertain`; the eval adapter
then collapsed `uncertain` into the three-class eval `split` label because
`Winner` has no `uncertain` enum. That made the prediction JSONLs look like
uniform `split` predictions even though the model had abstained.

Root cause:

- The no-RAG Ombudsman modes reused the cited/RAG Ombudsman system prompt,
  which required citing a similar determination.
- With no retrieved determinations in `kg_only`/`llm_only`, the model obeyed
  cite-or-abstain and returned `uncertain`.
- The parser also lacked robust Housing Ombudsman outcome normalisation
  (`service failure`, `maladministration`, `no maladministration`,
  `reasonable redress`) into the shared eval labels.

Fix applied after that diagnostic run:

- No-RAG Ombudsman modes now use an ablation-safe prompt: no invented
  determinations, `supporting_cases=[]`, and no abstention solely because
  retrieved citations are absent.
- Ombudsman outcome wording is normalised into eval labels:
  service failure/maladministration -> `tenant_wins`; no maladministration ->
  `landlord_wins`; partial/mixed/reasonable redress -> `split`.
- `predict_all.py` now emits diagnostic fields (`raw_overall_outcome`,
  `raw_overall_confidence`, `abstained`, and per-issue `raw_outcome`) while
  preserving compatibility with `eval.run`.

Re-run the live eval after this fix before using no-RAG ablation numbers in
SHA-68 or thesis material.

Post-fix smoke:

`housing_ombudsman_no_rag_wiring_smoke_20260504_201051` ran the first three
gold rows through `kg_only,llm_only` after the wiring fix. Raw outcomes were no
longer abstention-only:

- `kg_only`: 3/3 `tenant_win`, 0 abstentions.
- `llm_only`: 2/3 `tenant_win`, 1/3 `split`, 0 abstentions.

This smoke only proves the no-RAG wiring is no longer collapsing into
`uncertain -> split`; it is not a substitute for the full 50-case live rerun.

Post-fix full live rerun, 2026-05-04:

Artifacts:

- `eval/predictions/housing_ombudsman_stratified_50_live_20260504_202405_fixed/ordered/`
- `eval/results/housing_ombudsman_stratified_50_live_20260504_202405_fixed_ordered_full_eval/audit.json`
- `eval/results/housing_ombudsman_stratified_50_live_20260504_202405_fixed_ordered_full_eval/ablation.json`
- `eval/results/housing_ombudsman_stratified_50_live_20260504_202405_fixed_ordered_full_eval/summary.json`

Run method:

- `kg_only,llm_only` were run as two live shards each.
- `hybrid,rag_only` were run as five live shards each against the local
  Housing Ombudsman index with `--rag-index-root indices --top-k 5`.
- Shard outputs were merged and reordered to match
  `data/gold_standard/housing_repairs_social_v1.jsonl` before scoring.
- `OPENAI_TIMEOUT_SECONDS=600`, `seed=42`, `n_resamples=1000`,
  `min_case_count=50`.

Results, n=50:

| Mode | Accuracy | Accuracy 95% CI | Brier | Brier 95% CI | ECE | Amount@20% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| hybrid | 0.420 | [0.300, 0.560] | 0.238 | [0.222, 0.256] | 0.464 | 0.500 |
| rag_only | 0.540 | [0.400, 0.680] | 0.229 | [0.211, 0.246] | 0.456 | 0.560 |
| kg_only | 0.680 | [0.540, 0.800] | 0.323 | [0.306, 0.338] | 0.550 | 0.640 |
| llm_only | 0.680 | [0.540, 0.800] | 0.323 | [0.307, 0.338] | 0.550 | 0.600 |

Prediction distribution:

| Mode | Tenant | Landlord | Split | Raw abstentions |
| --- | ---: | ---: | ---: | ---: |
| hybrid | 21 | 1 | 28 | 10 |
| rag_only | 26 | 2 | 22 | 9 |
| kg_only | 33 | 2 | 15 | 1 |
| llm_only | 33 | 2 | 15 | 0 |

Confusion summary:

- Gold distribution is extremely tenant-heavy: `tenant=49`, `landlord=1`.
- `kg_only` and `llm_only` get `34/50` right: 33 tenant wins plus the single
  landlord win. They miss mainly by predicting `split` on tenant-win cases.
- `rag_only` gets `27/50` right: 26 tenant wins plus the landlord win.
- `hybrid` gets `21/50` right and predicts `split` on the only landlord-win
  case.

Interpretation:

- The no-RAG wiring bug is fixed. `kg_only` and `llm_only` are no longer
  abstention-only, and their 0.680 accuracy should be treated as the current
  live ablation baseline.
- The retrieval-backed modes are more conservative: they produce more `split`
  and `uncertain` raw outcomes after citation verification. That lowers
  accuracy on this tenant-heavy set.
- `rag_only` has the best Brier point estimate, but this is not enough to claim
  it is the better product behavior because its accuracy is materially lower
  and the set is only 50 cases.
- Hybrid still does not provide thesis-grade evidence for a RAG+KG improvement.
  The next product task is to inspect the retrieval/citation failure cases and
  tune issue-specific retrieval/prompting before reporting SHA-68 final numbers.
