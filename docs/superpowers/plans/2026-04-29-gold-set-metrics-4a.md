# Phase 4a — Accuracy + Calibration + Bootstrap CI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the three metrics that have no heavy ML dependencies, plus the bootstrap-CI helper that wraps every metric per SHA-97. Defer NLI hallucination audit (SHA-31) and RAGAS (SHA-29) to Phase 4b — those need transformers + torch + langchain and deserve their own scoped change.

**Architecture:** Pure functions in `packages/eval/metrics/`, each over `(gold_cases, predictions)` iterables. A single `Prediction` adapter dataclass (no coupling to orchestrator's `PredictionResult`). `eval.run` CLI orchestrates: load corpus → load predictions → compute metric with bootstrap CI → emit JSON report.

**Tech stack:** Python 3.9.6, numpy (already in `requirements.txt`), matplotlib (NEW dep — small, well-vetted, only needed for reliability_diagram PNG). No heavy ML deps in 4a.

**Out of scope for Phase 4a:** NLI citation/hallucination metric (deferred to Phase 4b — needs transformers + a model checkpoint). RAGAS metrics (Phase 4b — needs ragas + langchain stack). Real prediction integration with `PredictionEngineV2` (Phase 5 ablation runner).

---

## File structure

| File | Responsibility |
|---|---|
| `packages/eval/metrics/__init__.py` | Re-exports for ergonomic imports |
| `packages/eval/metrics/types.py` | `Prediction` dataclass adapter; `MetricResult` shape `(point, lower_95, upper_95, n)` |
| `packages/eval/metrics/accuracy.py` | `issue_winner_accuracy()`, `amount_within_threshold()` |
| `packages/eval/metrics/calibration.py` | `brier_score()`, `expected_calibration_error()`, `reliability_diagram()` |
| `packages/eval/metrics/uncertainty.py` | `bootstrap_ci()` helper (n_resamples=1000, seedable) |
| `packages/eval/run.py` | CLI: `python -m eval.run --metric {accuracy,brier,ece} --gold ... --predictions ...` |
| `packages/eval/tests/test_metrics_*.py` | One test file per metric module |
| `packages/eval/tests/fixtures/predictions_for_synthetic_corpus_10.jsonl` | Synthetic predictions matched to the Phase-3 10-case fixture |
| `docs/eval/metrics.md` | Usage doc — metric definitions, how to interpret outputs, CI integration |
| `requirements.txt` | Add `matplotlib>=3.7` |

---

## API design (locked before coding)

### `Prediction` adapter

```python
# packages/eval/metrics/types.py
@dataclass
class IssuePrediction:
    issue: str                    # must match GoldCase.claimed_amounts[].issue
    predicted_winner: Winner      # tenant / landlord / split
    win_probability: float        # P(landlord wins this issue), [0, 1]
    predicted_amount_gbp: Decimal # >=0


@dataclass
class Prediction:
    case_id: str                  # must match GoldCase.case_id
    overall_winner: Winner
    overall_win_probability: float  # P(landlord wins overall), [0, 1]
    total_predicted_gbp: Decimal
    per_issue: list[IssuePrediction]


@dataclass
class MetricResult:
    point: float                  # the metric value on the full sample
    lower_95: float               # bootstrap lower bound (point if no resampling)
    upper_95: float
    n: int                        # sample size used to compute the point estimate

    @property
    def survives_target(self) -> bool:
        # caller-defined; helper for thesis claim audit
        ...
```

### Metric signatures

```python
# packages/eval/metrics/accuracy.py
def issue_winner_accuracy(
    gold: list[GoldCase], predictions: list[Prediction]
) -> float:
    """Fraction of predicted per-issue winners that match ground truth.
    Pure scalar; wrap in bootstrap_ci() for the CI band."""

def amount_within_threshold(
    gold: list[GoldCase],
    predictions: list[Prediction],
    threshold_pct: float = 0.20,
) -> float:
    """Fraction of cases where total predicted GBP is within
    threshold_pct of the actual award."""


# packages/eval/metrics/calibration.py
def brier_score(
    gold: list[GoldCase], predictions: list[Prediction]
) -> float:
    """Mean of (P(landlord wins) - actual_landlord_won)^2 over all per-issue
    pairs. Lower is better. Bounded [0, 1]."""

def expected_calibration_error(
    gold: list[GoldCase],
    predictions: list[Prediction],
    n_bins: int = 10,
) -> float:
    """Sum over confidence bins of |bin_accuracy - bin_confidence| weighted
    by bin size."""

def reliability_diagram(
    gold: list[GoldCase],
    predictions: list[Prediction],
    out_path: Path,
    n_bins: int = 10,
) -> Path:
    """Render reliability diagram PNG to out_path. Returns out_path."""


# packages/eval/metrics/uncertainty.py
def bootstrap_ci(
    metric_fn: Callable[[list, list], float],
    gold: list[GoldCase],
    predictions: list[Prediction],
    *,
    n_resamples: int = 1000,
    seed: Optional[int] = 42,
    confidence: float = 0.95,
) -> MetricResult:
    """Resample (gold, prediction) PAIRS with replacement, recompute the
    metric, return MetricResult with point estimate from the full sample
    and CI bounds from the bootstrap distribution."""
```

### CLI

```bash
python -m eval.run --metric accuracy \
  --gold data/gold_standard/housing_v1.jsonl \
  --predictions eval/predictions/v1_run_001.jsonl \
  --out eval/results/accuracy_2026-04-29.json

python -m eval.run --metric brier \
  --gold ... --predictions ... \
  --no-bootstrap            # skip CI for fast iteration
```

Output JSON:

```json
{
  "metric": "issue_winner_accuracy",
  "gold_path": "...",
  "predictions_path": "...",
  "point": 0.78,
  "lower_95": 0.71,
  "upper_95": 0.85,
  "n": 50,
  "n_resamples": 1000,
  "seed": 42,
  "computed_at": "2026-04-29T16:30:00Z"
}
```

---

## Tasks

### Task 1: Types + bootstrap_ci helper (TDD)

**Files:** `packages/eval/metrics/{__init__.py, types.py, uncertainty.py}`, `tests/test_metrics_uncertainty.py`.

- [ ] **Step 1.1: Failing tests.** Cover `bootstrap_ci`:
  - Determinism with same seed: two calls return identical `MetricResult`.
  - Length invariance: empty input raises; n=1 input returns `lower_95 == upper_95 == point`.
  - Monotonicity: `lower_95 <= point <= upper_95`.
  - Plumbing: a constant metric (`lambda g, p: 0.5`) returns `point=0.5, lower=0.5, upper=0.5`.
  - Variability: a noisy metric returns `lower < upper` for n_resamples=1000 over n=50.

- [ ] **Step 1.2: Implement.** Use `random.Random(seed)` for deterministic resampling; `numpy.percentile` for CI bounds. Resample (gold[i], pred[i]) pairs with replacement.

- [ ] **Step 1.3: Commit.** `feat(eval): bootstrap_ci helper + Prediction adapter (SHA-97)`.

---

### Task 2: Accuracy metric (TDD)

**Files:** `packages/eval/metrics/accuracy.py`, `tests/test_metrics_accuracy.py`, fixture `predictions_for_synthetic_corpus_10.jsonl`.

- [ ] **Step 2.1: Failing tests.**
  - `issue_winner_accuracy` — perfect predictions → 1.0; all-wrong → 0.0; partial → exact fraction.
  - Cases with no `per_issue` (unapportioned path) — skipped or use overall_winner; document choice. Decision: use `overall_winner` for unapportioned cases (one comparison per case rather than per-issue).
  - `amount_within_threshold` — within 20% → counts; outside → doesn't.
  - Edge: gold/predictions length mismatch → ValueError with helpful message.
  - Edge: case_id mismatch in pair → ValueError.

- [ ] **Step 2.2: Build the synthetic predictions fixture.**

10-case prediction JSONL aligned with `synthetic_corpus_10.jsonl`. Mix of correct, incorrect, and partially correct predictions, calibrated around 70% accuracy so the metric returns a non-trivial number.

- [ ] **Step 2.3: Implement.**
- [ ] **Step 2.4: Coverage + run full suite.**
- [ ] **Step 2.5: Commit.** `feat(eval): issue_winner_accuracy + amount_within_threshold (SHA-30 partial)`.

---

### Task 3: Brier score (TDD)

**Files:** `packages/eval/metrics/calibration.py` (Brier only this task), `tests/test_metrics_calibration.py`.

- [ ] **Step 3.1: Failing tests.**
  - Perfect predictions (P=1.0 when landlord wins, 0.0 otherwise) → Brier 0.
  - Always 0.5 → Brier 0.25 (Brier of a coin flip).
  - Hand-computed: 3 issues with `(P, actual)` = `[(0.8, 1), (0.2, 0), (0.5, 1)]` → mean of `(0.04, 0.04, 0.25)` = `0.11`.
  - Empty input → ValueError.
  - Mismatched lengths → ValueError.

- [ ] **Step 3.2: Implement.**
- [ ] **Step 3.3: Commit.** `feat(eval): brier_score metric (SHA-30 partial)`.

---

### Task 4: ECE + reliability diagram (TDD)

**Files:** modify `calibration.py`, modify `tests/test_metrics_calibration.py`. Add `matplotlib` to `requirements.txt`.

- [ ] **Step 4.1: Failing tests.**
  - ECE: well-calibrated predictions over 10 bins → near 0.
  - ECE: systematically over-confident → positive value.
  - Reliability diagram: `out_path.exists()` after call; `Pillow.open()` confirms PNG signature.
  - `n_bins=1` edge case → should still work; whole sample collapses to one bin.

- [ ] **Step 4.2: Add `matplotlib>=3.7` to `requirements.txt`** (group: development / eval). Install in venv.

- [ ] **Step 4.3: Implement ECE** — bin by `win_probability`, compute weighted `|accuracy - confidence|` per bin.

- [ ] **Step 4.4: Implement `reliability_diagram`** — matplotlib bar plot, save PNG. No interactive mode; `Agg` backend.

- [ ] **Step 4.5: Commit.** `feat(eval): ECE + reliability_diagram PNG (SHA-30)`.

---

### Task 5: `eval.run` CLI orchestrator (TDD)

**Files:** `packages/eval/run.py`, `tests/test_run_cli.py`.

- [ ] **Step 5.1: Failing tests** (subprocess-based).
  - `python -m eval.run --metric accuracy --gold ... --predictions ...` exits 0 and prints JSON to stdout (or `--out PATH` writes file).
  - JSON shape: `{metric, gold_path, predictions_path, point, lower_95, upper_95, n, n_resamples, seed, computed_at}`.
  - `--no-bootstrap` flag → `lower_95 == upper_95 == point`, `n_resamples=0`.
  - Unknown metric → exit 2, helpful message.
  - Mismatched gold/predictions case_ids → exit 1, error to stderr.

- [ ] **Step 5.2: Implement.** Argparse subcommand-less CLI (single command with required `--metric`); load gold via `eval.dataset.load`; load predictions via a tiny `_load_predictions(path)` helper; dispatch to the named metric; wrap in `bootstrap_ci` unless `--no-bootstrap`.

- [ ] **Step 5.3: Commit.** `feat(eval): eval.run CLI orchestrator with bootstrap CI`.

---

### Task 6: Re-exports + docs

**Files:** `packages/eval/__init__.py`, `packages/eval/metrics/__init__.py`, `docs/eval/metrics.md`.

- [ ] **Step 6.1: Update re-exports** so `from eval.metrics import issue_winner_accuracy, brier_score, expected_calibration_error, reliability_diagram, bootstrap_ci, MetricResult, Prediction, IssuePrediction` works.

- [ ] **Step 6.2: Write `docs/eval/metrics.md`.** Cover:
  - What each metric measures, in plain English.
  - The thesis-claim survival rule (`accuracy_lower_95 > 0.70`, `brier_upper_95 < 0.20`, etc.).
  - Worked example using the synthetic 10-case fixture.
  - CI integration: `python -m eval.run --metric brier --strict-target 0.20 --out ...` (exit 1 if upper_95 ≥ 0.20). Implementation of `--strict-target` lands in Task 7 if time permits; otherwise document as a Phase 4b follow-up.
  - Pointer to Phase 4b: NLI citation audit + RAGAS metrics.

- [ ] **Step 6.3: Coverage evidence to `.sisyphus/evidence/eval/phase4a-coverage.txt`.**

- [ ] **Step 6.4: Commit.** `docs(eval): metrics package re-exports + usage doc`.

---

## Phase 4a exit checklist

- [ ] `bootstrap_ci()` ships with deterministic seed, length-invariance, monotonicity guarantees
- [ ] `issue_winner_accuracy()` and `amount_within_threshold()` ship with edge-case tests
- [ ] `brier_score()` ships with hand-computed regression test
- [ ] `expected_calibration_error()` ships with bin-collapse edge test
- [ ] `reliability_diagram()` writes a real PNG (verified via Pillow open)
- [ ] `python -m eval.run --metric {accuracy,brier,ece} ...` runs against the synthetic fixture
- [ ] Synthetic predictions fixture committed at `packages/eval/tests/fixtures/predictions_for_synthetic_corpus_10.jsonl`
- [ ] Re-exports work (`from eval.metrics import ...`)
- [ ] `docs/eval/metrics.md` published
- [ ] Coverage ≥ 80% on `packages/eval/metrics/`
- [ ] All Phase 1+2+3 tests still pass

Once all checked, halt. Linear tickets opened. PR drafted.

---

## Phase 4b (deferred — separate ticket)

NLI citation audit (SHA-31) and RAGAS metrics (SHA-29) ship in Phase 4b after Phase 4a is in main. Reasons to keep them separate:

1. **Heavy deps** — transformers + torch (~5GB) + ragas + langchain. Single PR keeps them isolated for CI and reviewer focus.
2. **Test data** — both metrics need realistic predictions WITH structured citations / contexts, which depends on Phase 5 prediction integration. Phase 4a metrics work against any prediction shape.
3. **Atomic claim units (SHA-94)** — the unsupported_claim_rate metric (SHA-31) needs the schema rework deferred from the original Codex review. Brainstorming session before Phase 4b.

Phase 4b is opened as SHA-105 at the end of Phase 4a.
