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

Next engineering step:

Wire `predict_all.py --engine live` to the actual Housing Ombudsman Chroma/BM25
retrieval namespace with target-source exclusion, add an Ombudsman issue mapping
for `disrepair`, regenerate independent predictions, and rerun this same bundle.
