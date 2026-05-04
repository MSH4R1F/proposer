# Housing Ombudsman Pilot Full Eval Run

This records the 2026-05-04 full accuracy/Brier/ECE/ablation run over the
currently adjudicated Housing Ombudsman pilot gold file.

Status update: this 10-case pilot has now been superseded by the reviewed
50-case baseline run documented in
`docs/eval/housing-ombudsman-stratified-50-full-eval.md`. Keep this page as the
first smoke-test record only.

Artifacts:

- `scripts/eval/run_full_eval.py`
- `data/gold_standard/housing_repairs_social_v1.jsonl`
- `eval/predictions/housing_ombudsman_gold_pilot_20260504/`
- `eval/results/housing_ombudsman_full_eval_20260504/audit.json`
- `eval/results/housing_ombudsman_full_eval_20260504/ablation.json`
- `eval/results/housing_ombudsman_full_eval_20260504/summary.json`

Run command:

```bash
venv/bin/python scripts/eval/run_full_eval.py \
  --gold data/gold_standard/housing_repairs_social_v1.jsonl \
  --predictions-dir eval/predictions/housing_ombudsman_gold_pilot_20260504 \
  --out-dir eval/results/housing_ombudsman_full_eval_20260504 \
  --domain housing.repairs_social.v1 \
  --seed 42 \
  --n-resamples 1000 \
  --min-case-count 10
```

Results, n=10:

| Mode | Accuracy | Accuracy 95% CI | Brier | Brier 95% CI | ECE | Amount@20% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| hybrid | 0.600 | [0.300, 0.900] | 0.202 | [0.067, 0.378] | 0.363 | 1.000 |
| rag_only | 0.600 | [0.300, 0.900] | 0.209 | [0.098, 0.336] | 0.418 | 1.000 |
| kg_only | 0.300 | [0.000, 0.600] | 0.229 | [0.181, 0.284] | 0.469 | 1.000 |
| llm_only | 0.300 | [0.000, 0.600] | 0.263 | [0.229, 0.295] | 0.510 | 1.000 |

Interpretation:

- Hybrid and RAG-only tie on point accuracy.
- Hybrid has a slightly better Brier point estimate than RAG-only, but the
  confidence intervals are wide and overlap.
- Hybrid/RAG-only beat KG-only/LLM-only on point accuracy, but this is not yet a
  defensible thesis claim because the pilot has only 10 cases.
- The Brier point estimate for hybrid is just above the target threshold of
  0.20, and the upper CI is far above it, so the calibration target does not
  land on this pilot.

Important limitations:

- `data/eval/housing_ombudsman_stratified_50.jsonl` is still a selection
  manifest, not adjudicated gold, so it cannot be scored for accuracy/Brier yet.
- The current scored file has 10 pilot `GoldCase` rows. Treat this as an
  end-to-end harness run, not final product evidence.
- The existing prediction JSONLs are pilot artifacts, not a live production
  hybrid-RAG run. Do not use these numbers as thesis results until live
  prediction wiring and leakage exclusion are complete.
- `amount@20% = 1.000` is not meaningful evidence yet because the pilot
  prediction artifacts are not independent enough for settlement-amount claims.
- The dataset audit is not clean under the legacy deposit stratification floor:
  `is_clean=false` due to missing deposit claim-type strata, with no leakage
  violations. This is acceptable for the non-strict pilot run only.

Next promotion step: label the stratified 50 into reviewed
`GoldCase` rows with `LabelingProvenance`, generate fresh independent
predictions for all four modes, then rerun this command with
`--min-case-count 50`.
