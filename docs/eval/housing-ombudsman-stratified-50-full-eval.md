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

Follow-up debug log:

- `docs/eval/housing-ombudsman-hybrid-debug-log.md` records the 2026-05-05
  root-cause analysis for the low `hybrid` score, the fixes applied to KG
  wiring and repairs retrieval, and the first 5-case live smoke result after
  the patch. The full 50-case live eval was rerun later on 2026-05-05 and is
  recorded below.

Post-hybrid-fix full live rerun, 2026-05-05:

Artifacts:

- `eval/predictions/housing_ombudsman_stratified_50_live_20260505_005603_hybrid_fix/`
- `eval/results/housing_ombudsman_stratified_50_live_20260505_005603_hybrid_fix_full_eval/audit.json`
- `eval/results/housing_ombudsman_stratified_50_live_20260505_005603_hybrid_fix_full_eval/ablation.json`
- `eval/results/housing_ombudsman_stratified_50_live_20260505_005603_hybrid_fix_full_eval/summary.json`

Post-result leakage audit and eval hardening, 2026-05-05:

Finding:

- `kg_only=1.000` is real under the old metric but not meaningful KG evidence.
  The gold distribution is `tenant=49`, `landlord=1`, `split=0`, so an
  always-tenant baseline scores `0.980`.
- The promoted Ombudsman gold rows also copied the final compensation/order
  amount into `disputed_amount_gbp` and `claimed_amounts`. That made
  `claim_amount_copy` score `amount@GBP100=1.000` in the smoke report, proving
  amount leakage in the old gold/input path.
- No mode-wiring bug was found: `kg_only` was not secretly retrieving RAG
  cases or reading `ground_truth_outcome`. The problem was dataset skew plus
  outcome-derived amount fields being reconstructed as intake facts.

Fixes applied:

- `prepare_housing_ombudsman_gold_review.py` now keeps final compensation only
  in `ground_truth_outcome.total_awarded_gbp`; draft `disputed_amount_gbp` is
  `null`, `case_size` is `unknown`, and `claimed_amounts` is empty unless a
  clean pre-decision claim amount exists.
- `GoldCase` now permits `case_size="unknown"`, `disputed_amount_gbp=null`,
  and empty `claimed_amounts` for `housing.repairs_social.v1`.
- `gold_case_to_case_file()` suppresses already-promoted legacy Ombudsman
  outcome-derived amount fields, so current rows no longer leak final awards
  into prediction CaseFiles.
- `IssuePredictor` no longer falls back from missing `predicted_amount` to
  `issue.claimed_amount`; missing model amounts stay unknown.
- Eval amount metrics now include amount@20%, amount@GBP100, MAE, median
  absolute error, signed bias, and coverage counters.
- `eval.ablate` now reports deterministic baselines:
  `always_tenant`, `always_landlord`, `claim_positive_winner`, and
  `claim_amount_copy`.
- The deterministic claim-copy baselines now reuse the same legacy Ombudsman
  amount suppression as `gold_case_to_case_file()`, so outcome-derived
  compensation copied into old pre-decision fields is not counted as a real
  claimant demand.
- `build_housing_ombudsman_stratified_eval.py` has
  `--allocation balanced_outcome` for the next 50-case set. A smoke run over
  the 1,000-case corpus produced: `maladministration=8`,
  `outside-jurisdiction=6`, `reasonable-redress=8`,
  `resolved-with-intervention=7`, `service-failure=7`,
  `severe-maladministration=7`, `unknown=7`.

Verification:

- Full eval test suite: `566 passed`.
- LLM orchestrator focused tests: `20 passed`.
- Compile smoke: `compileall` over `packages/eval`, `issue_predictor.py`, and
  `scripts/eval` passed.
- Current 50-row adapter leak smoke: `rows_checked=50`, `leak_count=0`.
- Full-eval smoke over the existing prediction artifacts completed and emitted
  the new amount metrics plus baselines. Post-baseline-fix, `claim_amount_copy`
  is no longer supported on legacy Ombudsman amount fields
  (`amount_n=0`, `amount@GBP100=0.000`). The old prediction artifacts still
  reflect the old run; regenerate live predictions after these changes before
  making product or thesis claims.

Results, n=50:

| Mode | Accuracy | Accuracy 95% CI | Brier | Brier 95% CI | ECE | Amount@20% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| hybrid | 0.800 | [0.680, 0.900] | 0.228 | [0.205, 0.252] | 0.449 | 0.480 |
| rag_only | 0.780 | [0.680, 0.900] | 0.205 | [0.182, 0.228] | 0.423 | 0.500 |
| kg_only | 1.000 | [1.000, 1.000] | 0.360 | [0.360, 0.360] | 0.600 | 0.560 |
| llm_only | 0.980 | [0.920, 1.000] | 0.356 | [0.344, 0.360] | 0.580 | 0.700 |

Prediction distribution:

| Mode | Tenant | Landlord | Split | Raw abstentions |
| --- | ---: | ---: | ---: | ---: |
| hybrid | 40 | 1 | 9 | 9 |
| rag_only | 39 | 1 | 10 | 10 |
| kg_only | 49 | 1 | 0 | 0 |
| llm_only | 48 | 2 | 0 | 0 |

Interpretation:

- The hybrid wiring/retrieval fix materially improved the retrieval-backed
  modes: `hybrid` moved from `21/50` to `40/50`, and `rag_only` moved from
  `27/50` to `39/50`.
- `kg_only=1.000` and `llm_only=0.980` should not be overclaimed. The gold set
  is `49/50` tenant-favorable, so a tenant-heavy no-RAG prediction pattern can
  score extremely well on plain accuracy.
- Retrieval-backed modes still abstain on hard rows after citation
  verification. That keeps accuracy below no-RAG on this skewed set, but gives
  better Brier point estimates than no-RAG.

Leakage-cleaned full live rerun, 2026-05-05:

After the adapter, predictor, and deterministic baseline leakage fixes landed,
the live prediction artifacts were regenerated through the patched
`gold_case_to_case_file()` path. This is the current honest diagnostic run for
the reviewed 50-case Housing Ombudsman set.

Artifacts:

- `eval/predictions/housing_ombudsman_stratified_50_live_20260505_post_patch_topk5_sharded5/`
- `eval/results/housing_ombudsman_stratified_50_live_20260505_post_patch_topk5_sharded5_full_eval/audit.json`
- `eval/results/housing_ombudsman_stratified_50_live_20260505_post_patch_topk5_sharded5_full_eval/ablation.json`
- `eval/results/housing_ombudsman_stratified_50_live_20260505_post_patch_topk5_sharded5_full_eval/summary.json`

Run method:

- The 50 gold rows were split into five contiguous 10-case shards.
- Each shard ran `hybrid,rag_only,kg_only,llm_only` with `--engine live`,
  `--client openai`, `--rag-index-root indices`, and `--top-k 5`.
- Shard outputs were concatenated back into the original gold order before
  scoring.
- Scoring used `domain=housing.repairs_social.v1`, `seed=42`, and
  `n_resamples=1000`.

Results, n=50:

| Mode | Accuracy | Accuracy 95% CI | Brier | Brier 95% CI | ECE | Amount@20% | Amount@GBP100 | MAE GBP | Bias GBP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| hybrid | 0.680 | [0.560, 0.800] | 0.247 | [0.226, 0.269] | 0.469 | 0.100 | 0.180 | 520 | -466 |
| rag_only | 0.700 | [0.580, 0.820] | 0.234 | [0.213, 0.254] | 0.457 | 0.120 | 0.160 | 539 | -441 |
| kg_only | 0.000 | [0.000, 0.000] | 0.250 | [0.250, 0.250] | 0.480 | 0.040 | 0.120 | 708 | -708 |
| llm_only | 0.000 | [0.000, 0.000] | 0.250 | [0.250, 0.250] | 0.480 | 0.040 | 0.120 | 708 | -708 |

Gold and prediction distribution:

| Distribution | Tenant | Landlord | Split | Raw abstentions |
| --- | ---: | ---: | ---: | ---: |
| gold | 49 | 1 | 0 | n/a |
| hybrid predictions | 34 | 1 | 15 | 15 |
| rag_only predictions | 35 | 1 | 14 | 14 |
| kg_only predictions | 0 | 0 | 50 | 50 |
| llm_only predictions | 0 | 0 | 50 | 50 |

Deterministic baselines:

| Baseline | Accuracy | Brier | Amount supported? |
| --- | ---: | ---: | --- |
| always_tenant | 0.980 | 0.020 | no |
| always_landlord | 0.020 | 0.980 | no |
| claim_positive_winner | 0.000 | 0.250 | no |
| claim_amount_copy | 0.000 | 0.250 | no |

Interpretation:

- This run should be treated as leakage-cleaned diagnostic evidence, not final
  thesis proof. It is the first run where the promoted legacy Ombudsman award
  fields are suppressed before prediction.
- The old no-RAG scores were inflated by outcome-derived amount fields and
  dataset skew. In the clean run, `kg_only` and `llm_only` return abstention
  style `split` predictions for all rows. That collapse is a useful sanity
  check: no-RAG modes no longer have hidden access to the final award.
- `rag_only` is the strongest current live mode on this diagnostic set:
  `accuracy=0.700`, `brier=0.234`. `hybrid` is slightly worse:
  `accuracy=0.680`, `brier=0.247`.
- The always-tenant baseline beats every model on headline accuracy because the
  reviewed set is `49/50` tenant-favorable. Accuracy alone is therefore not a
  valid product or thesis headline on this corpus.
- Award prediction is weak. The gold mean award is about `GBP708`, while
  `hybrid` predicts about `GBP242` on average and `rag_only` about `GBP267`.
  Both retrieval-backed modes under-award by more than `GBP400` on average.
- Calibration remains weak. Brier is above the target `<0.20`, and ECE remains
  around `0.46-0.47`.

Thesis-safe wording:

> After leakage removal, no-RAG ablations no longer produce artificially high
> Housing Ombudsman performance. Retrieval-backed modes remain the only modes
> with meaningful predictive signal, but they do not beat a skew-exploiting
> always-tenant baseline on the current 50-case diagnostic set. The result is a
> negative but useful finding: the current pipeline is not yet thesis-grade
> evidence for hybrid RAG+KG superiority. The next work must target a balanced
> reviewed eval set, better repairs-specific retrieval, explicit Ombudsman
> outcome semantics, and a separate compensation-award prediction path.
