# Evaluation Harness Architecture

> Diagrams and module responsibilities. Skim before reading [`methodology.md`](methodology.md) — this is the picture that makes the methodology concrete.

## Top-level data flow

```text
┌─────────────────────────┐
│ Tribunal PDFs           │  raw decisions, OCR'd
│ data/raw/bailii/*.pdf   │
└────────────┬────────────┘
             │
             │ 1.  Reviewer runs `annotate.py template`
             │ 2.  Reviewer fills in JSON
             │ 3.  `annotate.py validate` → schema gatekeeper
             │ 4.  `annotate.py append`   → JSONL accumulator
             ▼
┌──────────────────────────────────────┐
│  Gold-standard corpus                │
│  data/gold_standard/housing_v1.jsonl │
│  one annotated GoldCase per line     │
└────────────┬─────────────────────────┘
             │
             │ `eval.dataset.load(...)`
             ▼
┌──────────────────────────────────────┐
│  list[GoldCase]                      │
└────────────┬──────────────┬──────────┘
             │              │
   ┌─────────┘              └──────────────┐
   │ train()/test()                        │ audit()
   ▼                                       ▼
list[GoldCase]                         AuditReport
(filtered by                           (leakage, stratification,
 decision_date)                         distributions, is_clean)
   │                                       │
   │ paired with                           │ → `eval/results/audit_*.json`
   │  list[Prediction]                     │   `.sisyphus/evidence/eval/`
   │ (from PredictionEngineV2,             │
   │  via Phase 5 ablation runner)
   ▼
┌──────────────────────────────────────┐
│  eval.metrics                        │
│  ├ accuracy.issue_winner_accuracy    │
│  ├ accuracy.amount_within_threshold  │
│  ├ calibration.brier_score           │
│  ├ calibration.expected_calibration… │
│  └ calibration.reliability_diagram   │
└────────────┬─────────────────────────┘
             │
             │ wrapped in
             │ uncertainty.bootstrap_ci(seed=42)
             ▼
┌──────────────────────────────────────┐
│  MetricResult                        │
│  (point, lower_95, upper_95, n,      │
│   n_resamples)                       │
└────────────┬─────────────────────────┘
             │
             │ python -m eval.run
             ▼
┌──────────────────────────────────────┐
│  eval/results/<metric>_<date>.json   │
│  → thesis_audit.py (Phase 4b)        │
│  → ablation comparison (Phase 5)     │
└──────────────────────────────────────┘
```

## Module dependency graph

```text
                        ┌─────────────────┐
                        │ eval.schema     │
                        │   GoldCase,     │
                        │   Provenance,   │
                        │   ClaimType,    │
                        │   RegionUK,     │
                        │   Authority,    │
                        │   etc.          │
                        └────────┬────────┘
                                 │ imports
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
   ┌─────────────────┐ ┌────────────────┐ ┌──────────────────┐
   │ eval.dataset    │ │ scripts.eval   │ │ eval.metrics     │
   │   load,         │ │  .annotate     │ │   .types         │
   │   train, test,  │ │   template,    │ │     Prediction,  │
   │   audit         │ │   validate,    │ │     IssuePred…,  │
   │   AuditReport   │ │   append, …    │ │     MetricResult │
   └────────┬────────┘ └────────────────┘ └────────┬─────────┘
            │                                      │
            │              ┌───────────────────────┼─────────────────────┐
            │              ▼                       ▼                     ▼
            │   ┌────────────────┐    ┌──────────────────┐  ┌──────────────────┐
            │   │ eval.metrics   │    │ eval.metrics     │  │ eval.metrics     │
            │   │  .accuracy     │    │  .calibration    │  │  .uncertainty    │
            │   │   issue_…,     │    │    brier_score,  │  │    bootstrap_ci  │
            │   │   amount_…     │    │    ECE,          │  │                  │
            │   │                │    │    reliability_… │  │                  │
            │   └────────┬───────┘    └─────────┬────────┘  └─────────┬────────┘
            │            └────────────────┬─────┴─────────────────────┘
            │                             ▼
            │                    ┌────────────────┐
            └───────────────────►│  eval.run      │
                                 │   CLI orch.    │
                                 │   --metric X,  │
                                 │   --gold ...,  │
                                 │   --predictions│
                                 └────────────────┘
```

**Direction of dependency:** every arrow points from "depends on" to "depended-upon". Nothing in `eval/` reaches outside the package, except the production CLI scripts which load from `eval/`.

**Decoupling:** `eval.metrics.types.Prediction` is intentionally NOT a re-export of `packages/llm_orchestrator/PredictionResult`. The Phase 5 adapter — `eval.adapter.from_prediction_result` — is the only file in `packages/eval/` that imports from `llm_orchestrator`. This is so:
- `packages/eval/` can be tested without spinning up the orchestrator stack.
- Schema changes in either package don't ripple into the other.

## File ownership

| Path | Owner | Notes |
|---|---|---|
| `packages/eval/**` | Track A (this track) | Every file in this PR series |
| `scripts/eval/**` | Track A | Annotation CLI |
| `data/gold_standard/**` | Track A (write); Reviewers (content) | Production corpus |
| `docs/eval/**` | Track A (drafted); Window 1 (indexed) | This file lives here |
| `packages/llm_orchestrator/pipeline/prediction_engine_v2.py` | Track B (read-only for us) | Source of `Prediction` objects we consume in Phase 5 |
| `packages/rag_engine/**` | Track C (read-only for us) | Retrieval — Phase 5 talks to it via `PredictionEngineV2` |
| `packages/kg_builder/**` | Track B (read-only for us) | KG — same as above |

The boundary rule: nothing in `packages/eval/` ever directly imports from rag_engine, kg_builder, or `prediction_engine_v2` — *except* `eval.adapter`, which imports the orchestrator's `PredictionResult` type to convert engine outputs into the `Prediction` shape. The follow-up live-runner (deferred) will call `PredictionEngineV2.predict()` outside the eval package and pipe results through `eval.adapter`.

## Phase 5 ablation pipeline

```text
                 list[GoldCase]
                       │
                       ├── shared across all modes ──┐
                       ▼                              ▼
        ┌──────────────────────────────────┐    ┌─────────────────┐
        │  predictions per mode            │    │ eval.compare    │
        │  ─ hybrid.jsonl                  │───►│  build_…_report │
        │  ─ rag_only.jsonl                │    │   loops:        │
        │  ─ kg_only.jsonl                 │    │     accuracy,   │
        │  ─ llm_only.jsonl                │    │     amount_…,   │
        └──────────────────────────────────┘    │     brier, ece  │
                       ▲                         │   per mode      │
                       │ adapted from            └────────┬────────┘
                       │ PredictionResult                 │
                       │ via eval.adapter         each metric wrapped in
                       │                          bootstrap_ci(seed=42)
                       │                                  ▼
                       │                         ┌─────────────────┐
                       │                         │ ComparisonReport│
                       │                         │  (n_cases, seed,│
                       │                         │   modes:[Mode…])│
                       │                         └────────┬────────┘
                       │                                  │
        ┌──────────────────────────────────┐              │ JSON
        │ live runner (DEFERRED to follow- │              ▼
        │ up PR; blocks on Phase 6 corpus  │     python -m eval.ablate
        │ + GoldCase→CaseFile constructor) │     → eval/results/ablation_*.json
        │   PredictionEngineV2.predict(    │              │
        │     mode=PredictionMode.HYBRID,  │              ▼
        │     case_file=…)                 │     SHA-68 RQ1 thesis table +
        └──────────────────────────────────┘     summarise_dominance() check
```

`summarise_dominance(a, b)` answers "X significantly better than Y" via non-overlapping bootstrap CIs. Higher-is-better metrics: `a.lower_95 > b.upper_95`. Lower-is-better metrics: `a.upper_95 < b.lower_95`. Overlap → `no_dominance`.

## Lifecycle of a single annotated case

```text
[Reviewer reads PDF]
        │
        │ sha256sum data/raw/bailii/case.pdf
        ▼
[Reviewer fills draft.json]
        │
        │ python scripts/eval/annotate.py validate draft.json
        ▼
       {valid?}
        │
        │ yes
        ▼
[python scripts/eval/annotate.py append draft.json]
        │
        │ → atomic JSONL append
        ▼
[data/gold_standard/housing_v1.jsonl gains 1 line]
        │
        │ Phase 6: another reviewer blind-annotates same case
        │ → row in docs/eval/reviewer-log.md if disagreement
        ▼
[Cohen's κ ≥ 0.8 per claim_type required for DoD]
        │
        ▼
[Case is downstream-consumable by every metric]
```

## Lifecycle of a single metric run

```text
[CI nightly] OR [Researcher local]
        │
        ▼
PYTHONPATH=packages python -m eval.run --metric brier \
    --gold     data/gold_standard/housing_v1.jsonl \
    --predictions  eval/predictions/<run>.jsonl \
    --seed 42 \
    --out eval/results/brier_2026-04-29.json
        │
        ▼
[load: eval.dataset.load() ............ → list[GoldCase]]
        │
        ▼
[parse predictions JSONL ............... → list[Prediction]]
        │
        ▼
[align: case_id pairing check (raises on mismatch)]
        │
        ▼
[bootstrap_ci(brier_score, gold, preds, n=1000, seed=42)]
        │
        │ for each of 1000 resamples:
        │   sample (gold[i], preds[i]) PAIRS with replacement
        │   recompute brier_score on the resample
        │
        ▼
[MetricResult(point, lower_95, upper_95, n=50, n_resamples=1000)]
        │
        ▼
[JSON to file or stdout]
```

## What's where in the test suite

| File | What it tests |
|---|---|
| `tests/test_schema.py` (47 tests) | Every enum, every leaf model, every cross-field invariant INV-1..10. Covers two synthetic fixtures (apportioned + unapportioned) and the synthetic 10-case corpus. |
| `tests/test_dataset.py` (40 tests) | `load` (lenient/strict), `train`/`test` filters, leakage check, full `audit` report, the dataset CLI subprocess, in-process unit tests for the dataset CLI. |
| `tests/test_annotate_cli.py` (16 tests) | Annotation CLI subprocess (template/validate/append/list/show) plus in-process unit tests for `_template`, `_cli_main`. |
| `tests/test_metrics_uncertainty.py` (10 tests) | `bootstrap_ci` determinism, length-invariance, monotonicity, edge cases. |
| `tests/test_metrics_accuracy.py` (14 tests) | `issue_winner_accuracy` perfect/wrong/partial, missing predictions, unapportioned path; `amount_within_threshold` default + custom thresholds + zero-actual edge. |
| `tests/test_metrics_calibration.py` (12 tests) | Brier perfect/coin-flip/hand-computed; ECE well-calibrated/over-confident/n_bins=1; reliability diagram PNG output verified by signature; end-to-end against synthetic corpus. |
| `tests/test_run_cli.py` (14 tests) | `eval.run` against synthetic corpus + predictions for every metric, `--no-bootstrap`, `--out`, `--seed`, alignment failure, in-process coverage. |
| `tests/test_adapter.py` (19 tests) | `from_prediction_result` mappings: outcome→Winner, confidence→P(landlord), unknown-outcome fail-fast, amount aggregation, calibrated_confidence override, IssueType-enum unwrap, case_id round-trip. |
| `tests/test_compare.py` (15 tests) | `build_comparison_report` shape, metric correctness on perfect/coinflip predictions, ranking by alias, bootstrap integration + seed determinism, dominance check. |
| `tests/test_ablate_cli.py` (16 tests) | `eval.ablate` CLI: arg parsing (`mode=path`), in-process orchestration, numeric flag validation, two-mode aggregation, ranking, alignment failure, seed recording, subprocess entry point. |
| `tests/test_ablation_fixtures.py` (4 tests) | Regression check on the synthetic per-mode prediction fixtures — locks the accuracy ranking `hybrid > rag_only > kg_only > llm_only`. |

248 tests total. ~99% line coverage on `packages/eval/`.

## Phase boundaries

```text
Phase 1 ─────┬─── Phase 2 ─────┬─── Phase 3 ─────┬─── Phase 4a ────┬─── Phase 5 ────┬─── Phase 4b/5b
             │                  │                 │                 │                  │  (deferred)
schema.py    │  dataset.py      │ scripts/eval/   │ metrics/{accuracy │ adapter.py     │ NLI hallucination,
+ tests      │  + tests + CLI   │  annotate.py    │  ,calibration,    │ compare.py     │ RAGAS, atomic
+ schema doc │  + dataset doc   │  + reviewer     │  uncertainty}     │ ablate.py CLI  │ claims schema;
             │                  │  guide          │  + run.py         │ + per-mode     │ live runner +
             │                  │  + 10-case      │  + metrics doc    │   fixtures     │ GoldCase→
             │                  │   fixture       │                   │ + ablation doc │ CaseFile
             ▼                  ▼                 ▼                   ▼                  ▼
        53 tests             80 tests         133 tests            181 tests          248 tests
```
