# Metrics — Phase 4a (Accuracy + Calibration + Bootstrap CI)

> Phase 4b (NLI hallucination, RAGAS) is deferred — separate ticket SHA-105 (or whichever ID lands), pending the heavy ML deps and the atomic claim-units design (SHA-94).

## What ships in 4a

| Metric | Function | Module | Linear |
|---|---|---|---|
| Issue-level winner accuracy | `issue_winner_accuracy()` | `eval.metrics.accuracy` | SHA-30 (partial) |
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
