# Metrics — Phase 4a (Accuracy + Calibration + Bootstrap CI)

> Phase 4b (NLI hallucination, RAGAS) is deferred — separate ticket SHA-105 (or whichever ID lands), pending the heavy ML deps and the atomic claim-units design (SHA-94).

## What ships in 4a

| Metric | Function | Module | Linear |
|---|---|---|---|
| Issue-level winner accuracy | `issue_winner_accuracy()` | `eval.metrics.accuracy` | SHA-30 (partial) |
| Balanced accuracy | `balanced_accuracy()` | `eval.metrics.accuracy` | Hybrid RAG investigation 2026-05-05 |
| Macro-F1 | `macro_f1()` | `eval.metrics.accuracy` | Hybrid RAG investigation 2026-05-05 |
| Abstention rate | `abstention_rate()` | `eval.metrics.accuracy` | Hybrid RAG investigation 2026-05-05 |
| Covered accuracy | `covered_accuracy()` | `eval.metrics.accuracy` | Hybrid RAG investigation 2026-05-05 |
| Coverage-adjusted accuracy | `coverage_adjusted_accuracy()` | `eval.metrics.accuracy` | Hybrid RAG investigation 2026-05-05 |
| £-amount within threshold | `amount_within_threshold()` | `eval.metrics.accuracy` | SHA-30 (partial) |
| £-amount within absolute band | `amount_within_absolute_threshold()` | `eval.metrics.accuracy` | SHA-30 (partial) |
| £-amount mean absolute error | `amount_mae_gbp()` | `eval.metrics.accuracy` | SHA-30 (partial) |
| £-amount median absolute error | `amount_median_absolute_error_gbp()` | `eval.metrics.accuracy` | SHA-30 (partial) |
| £-amount signed bias | `amount_mean_signed_error_gbp()` | `eval.metrics.accuracy` | SHA-30 (partial) |
| £-amount coverage counters | `amount_coverage()` | `eval.metrics.accuracy` | SHA-30 (partial) |
| Brier score | `brier_score()` | `eval.metrics.calibration` | SHA-30 |
| Expected Calibration Error (ECE) | `expected_calibration_error()` | `eval.metrics.calibration` | SHA-30 |
| Reliability diagram (PNG) | `reliability_diagram()` | `eval.metrics.calibration` | SHA-30 |
| Bootstrap CI helper | `bootstrap_ci()` | `eval.metrics.uncertainty` | SHA-97 (partial) |

All metric functions are pure — no I/O. They return scalars. Wrap in `bootstrap_ci()` for the CI band.

## Inputs

Every metric takes two arguments:

- `gold: list[GoldCase]` — typically from `eval.dataset.load(...).cases`.
- `predictions: list[Prediction]` — `eval.metrics.Prediction` adapter (intentionally NOT a re-export of the orchestrator's `PredictionResult` to keep `packages/eval/` decoupled).

Both lists must be the **same length** and **aligned by case_id in order**. The CLI validates this and raises with a clear error if not. The Phase 5 ablation runner is responsible for emitting predictions in the right order.

## Apportioned vs unapportioned

Apportioned cases (gold `per_issue` non-empty) are scored **per issue**. Unapportioned cases (per_issue empty + `unapportioned_reason` set) collapse to **one comparison per case** using `overall_winner` and `overall_win_probability`.

Missing per-issue predictions (predicted `per_issue` lacks an issue label that gold has) count as **wrong** for accuracy and contribute `(P=0.5, actual)` to calibration metrics — i.e. silence is treated as maximum uncertainty, not as a free pass.

## Imbalance And Abstention Metrics

The Housing Ombudsman diagnostic set exposed that headline accuracy can hide
both class skew and abstention. The full ablation report now also emits:

- `balanced_accuracy` — macro-average recall over labels present in gold.
- `macro_f1` — macro-F1 over labels present in either gold or predictions, so
  spurious `split` predictions on a no-split gold set are visible.
- `abstention_rate` — fraction of comparisons where the raw orchestrator output
  was `uncertain` or explicitly marked `abstained`.
- `covered_accuracy` — accuracy over non-abstained comparisons only.
- `coverage_adjusted_accuracy` — correct non-abstained answers divided by all
  comparisons.

`covered_accuracy` must always be read beside `abstention_rate`; a model can be
very accurate when it answers while still being too quiet for product use.

## Amount Metrics

Amount scoring is case-level and uses `ground_truth_outcome.total_awarded_gbp`
as the gold amount. Prediction amounts may be `null`. A `null` prediction is
not silently coerced to £0: threshold metrics count it as a miss, and
`amount_coverage()` reports it under `missing_predicted_amount`.

The full ablation report now emits:

- `amount.within_20pct` — predicted total within ±20% of the actual award.
- `amount.within_gbp100` — predicted total within ±£100 of the actual award.
- `amount.mae_gbp` — mean absolute error over evaluable amount pairs.
- `amount.median_absolute_error_gbp` — median absolute error over evaluable amount pairs.
- `amount.mean_signed_error_gbp` — positive means over-prediction; negative means under-prediction.
- `amount.coverage` — case counts for available gold amounts, available predicted amounts, and evaluable pairs.

Always read error metrics together with coverage. If `n_evaluable=0`, the
error point estimate is not product evidence even though it renders as `0.0`
for JSON compatibility.

## Deterministic Baselines

`eval.ablate` also reports non-LLM baselines beside model modes:

- `always_tenant`
- `always_landlord`
- `claim_positive_winner`
- `claim_amount_copy`

These baselines are deliberate tripwires. If a model only beats weak baselines
because the gold set is skewed, or if `claim_amount_copy` scores perfectly,
the eval is telling us the dataset/prediction inputs are too easy or leaky.
For legacy Housing Ombudsman rows, `claim_amount_copy` suppresses
outcome-derived compensation amounts copied into pre-decision fields, so those
old artifact leaks show up as unsupported amount baselines instead of perfect
amount scores.

## Bootstrap confidence intervals (SHA-97)

Per the [interim report](../../interim-report) and the strategic plan, every thesis claim must survive bootstrap resampling on `n=50` before it lands. `bootstrap_ci()` resamples `(gold[i], predictions[i])` PAIRS with replacement (preserving case-level dependencies between issue-level pairs), recomputes the metric per resample, and returns:

```python
@dataclass
class MetricResult:
    point: float
    lower_95: float
    upper_95: float
    n: int
    n_resamples: int
```

**Determinism:** `bootstrap_ci(..., seed=42)` returns byte-identical results across runs. Default seed is 42; set explicitly for reproducibility in CI.

**Edge cases:** empty input raises; `n=1` returns a degenerate CI where `lower == upper == point`; `n_resamples=0` short-circuits to the same.

## Thesis-claim survival rule

A claim only "lands" in the thesis if its lower CI bound clears the headline target.

| Headline target | Condition for the claim to land |
|---|---|
| Accuracy > 70% | `accuracy_lower_95 > 0.70` |
| Brier < 0.20 | `brier_upper_95 < 0.20` |
| Hallucination < 2% | `unsupported_lower_95 < 0.02` (Phase 4b) |

Implementation of the claim-survival audit lives at `scripts/eval/thesis_audit.py` (Phase 4b). For now, manually inspect `lower_95` / `upper_95` in the run report.

## CLI

```bash
# Default: bootstrap with n=1000, seed=42
PYTHONPATH=packages python -m eval.run --metric accuracy \
  --gold data/gold_standard/housing_v1.jsonl \
  --predictions eval/predictions/v1_run_001.jsonl

# Skip bootstrap (fast iteration during development)
PYTHONPATH=packages python -m eval.run --metric brier ... --no-bootstrap

# Write report to file instead of stdout
PYTHONPATH=packages python -m eval.run --metric ece ... --out eval/results/ece_2026-04-29.json

# Reproducible: pin the seed
PYTHONPATH=packages python -m eval.run --metric accuracy ... --seed 7
```

Output JSON:

```json
{
  "metric": "issue_winner_accuracy",
  "metric_alias": "accuracy",
  "gold_path": "...",
  "predictions_path": "...",
  "point": 0.78,
  "lower_95": 0.71,
  "upper_95": 0.85,
  "n": 50,
  "n_resamples": 1000,
  "seed": 42,
  "computed_at": "2026-04-29T16:30:00+00:00"
}
```

Exit codes: `0` = success, `1` = alignment error or empty gold, `2` = unknown metric (argparse).

## Worked example — synthetic 10-case fixture

```bash
$ PYTHONPATH=packages python -m eval.run --metric brier \
    --gold packages/eval/tests/fixtures/synthetic_corpus_10.jsonl \
    --predictions packages/eval/tests/fixtures/predictions_for_synthetic_corpus_10.jsonl \
    --no-bootstrap

{
  "metric": "brier_score",
  "metric_alias": "brier",
  "point": 0.185,
  "lower_95": 0.185,
  "upper_95": 0.185,
  "n": 10,
  "n_resamples": 0,
  ...
}
```

The synthetic predictions are deliberately noisy — Brier 0.185 is between perfect (0.0) and coin-flip (0.25). Real predictions from `PredictionEngineV2` will land somewhere on this scale.

## CI integration (target shape)

A nightly job runs:

```bash
PYTHONPATH=packages python -m eval.dataset audit data/gold_standard/housing_v1.jsonl --strict
PYTHONPATH=packages python -m eval.run --metric accuracy --gold ... --predictions ... --out eval/results/accuracy_$(date +%F).json
PYTHONPATH=packages python -m eval.run --metric brier    --gold ... --predictions ... --out eval/results/brier_$(date +%F).json
PYTHONPATH=packages python -m eval.run --metric ece      --gold ... --predictions ... --out eval/results/ece_$(date +%F).json
```

The thesis-claim survival audit (Phase 4b) consumes those JSON reports. Brier-regression guard in CI (>0.05 vs main) is also Phase 4b.

## Phase 4b preview

The deferred metrics need heavier infrastructure:

- **NLI citation entailment** (SHA-31) — needs `transformers` + a DeBERTa-v3-mnli checkpoint (~1 GB). Also requires the atomic-claim-units schema redesign from SHA-94.
- **RAGAS metrics** (SHA-29) — `ragas` library brings `langchain` and friends. Real test data needs Phase 5 prediction integration.

These will be opened as a separate sub-issue once 4a is in main.

## Related

- [`docs/eval/gold-schema.md`](gold-schema.md) — what `gold[i]` looks like.
- [`docs/eval/dataset.md`](dataset.md) — how to load the corpus + the audit.
- `docs/superpowers/plans/2026-04-29-gold-set-metrics-4a.md` — the bite-sized TDD plan that built this.

## Determination metrics (housing.repairs_social.v1)

Added 2026-05-06. Companion to [`docs/eval/housing-ombudsman-determination-ontology-2026-05-06.md`](housing-ombudsman-determination-ontology-2026-05-06.md).

- `determination_accuracy(gold, predictions) -> float` — fraction of correct determination predictions on cases that carry a gold determination. Cases without `gold.ground_truth_outcome.determination` (legacy rows) are excluded from the denominator. Missing predictions count as wrong. Returns `0.0` when no gold determinations are present.
- `determination_class_recall(gold, predictions) -> dict[Determination, float]` — per-Determination recall. Classes absent from the gold subset are omitted. Returns `{}` when no gold determinations are present.
- `amount_mae_gbp_by_construct(gold, predictions, construct: str) -> float` — MAE in GBP restricted to cases whose gold amount lives in the named construct (`"ordered_now"`, `"previously_offered"`, or `"global_unapportioned"`). Differs from `amount_mae_gbp` in two ways: (1) the gold side reads from the corresponding split field rather than `total_awarded_gbp`; (2) a missing prediction is counted as a full-magnitude error (`actual` GBP) when actual > 0, rather than excluded — this avoids inflating the visible MAE when the model abstains on every reasonable-redress case it should have predicted.

Headline `housing.repairs_social.v1` metrics for thesis-grade reporting (per the [balanced-50 root-cause investigation](housing-ombudsman-balanced-50-root-cause-investigation-2026-05-06.md) §6 acceptance gates):

| Metric | Replaces (legacy housing) | Why |
|---|---|---|
| `determination.accuracy` | binary `accuracy` | Construct-stable across the 7 Ombudsman determination classes; the binary winner is a lossy projection of the manifest tag. |
| `determination.class_recall` | — | Per-class recall — the only way to surface "is the model honest about reasonable-redress?" or "does the model abstain on outside-jurisdiction?" |
| `amount.mae_gbp_ordered_now` | `amount.mae_gbp` | Scores fresh compensation orders only — the construct the model is actually asked to predict. |
| `amount.mae_gbp_previously_offered` | (new) | Captures landlord pre-offer extraction quality (when the model surfaces an estimate). Useful for the reasonable-redress class. |
| `amount.mae_gbp_global_unapportioned` | (new) | Settlement / resolved-with-intervention totals. |
| `amount.within_gbp100` | retained | Calibrated on construct-matched amount only when the per-construct MAE is the headline. |

Legacy metrics (`accuracy`, `covered_accuracy`, `amount.mae_gbp`) are still emitted in `summary.json` for backward compatibility. They should not be the headline number on `housing.repairs_social.v1`.

### Live numbers from a 2026-05-06 run

[`docs/eval/housing-ombudsman-stratified-50-v2-eval-2026-05-06.md`](housing-ombudsman-stratified-50-v2-eval-2026-05-06.md) is the canonical worked example. Concrete reading guide for the four most-misunderstood numbers:

- **`accuracy` is corpus-imbalance-sensitive.** On the stratified-50 v2 corpus the `always_tenant` baseline scores 0.979 (47/48 rows are tenant-wins under the legacy binary). Hybrid's 0.812 looks worse than this baseline only because hybrid abstains on some cases and sometimes confidently predicts landlord/split based on retrieval. The no-RAG modes (kg_only / llm_only) hit 0.958 on the same axis precisely *because* they default to tenant — closer to the imbalance baseline. Don't compare modes via `accuracy` on housing — use `determination.accuracy` or `balanced_accuracy`.
- **`covered_accuracy` is selection-bias-sensitive.** A mode that abstains on the borderline cases will score higher on covered_accuracy than a mode that tries those cases. On the same run, `llm_only` Run 1 (pre-narrative-fix) hit 1.000 covered_accuracy on 8 of 48 cases — that's not a useful comparison number, just an artefact of heavy abstention. Pair covered_accuracy with `abstention_rate` or use `coverage_adjusted_accuracy`.
- **`determination.accuracy` is construct-stable and inverts the legacy ranking on this corpus.** Direct fraction-correct on the 7-class Ombudsman ontology. Hybrid + rag_only **0.500** beat kg_only + llm_only **0.417** — retrieval helps when scored against the construct-stable axis even when it appears to hurt on the legacy binary. Reads honestly across rebalanced corpora because the classes are intrinsic to the source determinations rather than a polysemous binary.
- **`amount.mae_gbp_ordered_now` is the construct-matched amount metric.** Restricted to cases where the gold amount represents a fresh Ombudsman compensation order (the construct the model's prompt actually targets). Hybrid £488 in the worked example. The legacy all-rows `amount.mae_gbp` (£587 on the same run) is contaminated by reasonable_redress and resolved_with_intervention rows the model can't see prior offers for.

Deposit-style baselines (`claim_positive_winner`, `claim_amount_copy`) emit `null` (rendered as `n/a`) on housing gold because the deposit construct does not apply — see `packages/eval/compare.py::_baseline_metric_value`.
