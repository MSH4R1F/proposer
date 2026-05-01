# Ablation runner — Phase 5 (SHA-32)

> The RQ1 ablation report — does the hybrid pipeline beat RAG-only / KG-only / LLM-only? — is produced by `python -m eval.ablate`. This doc covers the methodology, the CLI, and a worked example on the synthetic 10-case corpus.

## Why an ablation

The thesis claim "hybrid > RAG-only / KG-only" needs a defensible comparison. Just reporting that hybrid hit 75% accuracy doesn't tell you the contribution of each component. An ablation isolates the contribution by running the same evaluation against each mode of the prediction engine:

| Mode | What it does |
|---|---|
| **HYBRID** | KG-aware retrieval + KG fact card in prompt (production default) |
| **RAG_ONLY** | IssueDecomposer ignores the KG; retrieval has no KG filter; no fact card |
| **KG_ONLY** | Skip RAG entirely; LLM reasons from KG fact card + kg_constraints alone |
| **LLM_ONLY** | Skip both KG and RAG; bare CaseFile prompt — control baseline |

The mode flag is wired into `PredictionEngineV2.predict(case_file, mode=...)` (SHA-33, landed on main).

## What ships in Phase 5

- `eval.adapter.from_prediction_result(result) → Prediction` — the seam between `packages/llm_orchestrator/` and `packages/eval/`. Maps `OutcomeType` → `Winner`, converts outcome-confidence to `P(landlord wins)`, aggregates amounts.
- `eval.compare.build_comparison_report(gold, predictions_by_mode, ...)` — runs `accuracy`, `amount_within_threshold`, `brier`, and `ece` for every mode under bootstrap CIs.
- `eval.compare.summarise_dominance(a, b)` — per-metric significance check via non-overlapping CIs.
- `eval.ablate` — CLI wrapper that takes one prediction JSONL per mode and emits the comparison report.
- Synthetic per-mode prediction fixtures so CI demonstrates the full pipeline without LLM calls.

## What ships in Phase 5b (live-runner follow-up)

- `eval.issue_alignment` — bidirectional `ClaimType` ↔ `DisputeIssue` map; `UnmappableIssue` exception for the gaps (`disrepair`, `end_of_tenancy`, orchestrator-only values like `garden`).
- `eval.case_file_adapter.gold_case_to_case_file(gold) → LossyReconstruction` — reconstructs a *pre-decision* CaseFile from a *post-decision* GoldCase, dropping every artifact that would let the engine cheat (`ground_truth_outcome`, `key_reasoning_quotes`, tribunal `statutory_basis`, tribunal `cited_authorities`, `decision_date`). It also records a non-leaky `ClaimType → claimed_amounts.issue` map when the labels are one-to-one, so runner output can join against gold per-issue labels.
- `eval._stub_prediction.make_stub_prediction(case_file, mode)` — deterministic per-mode `PredictionResult` stand-in (no LLM); used by `--engine stub` so CI exercises the full chain.
- `scripts/eval/predict_all.py` — loops `(gold_case, mode)` through reconstruction → predict → adapt → JSONL. `--engine stub` (CI default) and `--engine live` (deferred, raises until an LLM client is wired in). Stdout reports per-mode counts and unmappable claim-type tallies (alignment diagnostics).

What still does **not** ship: the **real LLM runner** wiring (concrete `BaseLLMClient` + key handling). That's a project-level decision (Anthropic vs OpenAI vs both, key management) and will be resolved in a follow-up before the thesis ablation table is generated against the real Phase 6 corpus.

### End-to-end pipeline

```bash
# 1. Run the (stub) prediction loop over the gold corpus
PYTHONPATH=packages python scripts/eval/predict_all.py \
    --gold      data/gold_standard/housing_v1.jsonl \
    --out-dir   eval/predictions/run_2026-05-01 \
    --engine    stub          # or 'live' once your LLM client is wired
    # --modes hybrid,rag_only,kg_only,llm_only   (default: all four)
    # --limit  10                                 (smoke testing)

# 2. Feed the four JSONLs into eval.ablate
PYTHONPATH=packages python -m eval.ablate \
    --gold        data/gold_standard/housing_v1.jsonl \
    --predictions hybrid=eval/predictions/run_2026-05-01/hybrid.jsonl \
    --predictions rag_only=eval/predictions/run_2026-05-01/rag_only.jsonl \
    --predictions kg_only=eval/predictions/run_2026-05-01/kg_only.jsonl \
    --predictions llm_only=eval/predictions/run_2026-05-01/llm_only.jsonl \
    --out         eval/results/ablation_2026-05-01.json
```

The Phase 5b integration test (`packages/eval/tests/test_predict_all.py::TestOutputAblationCompatible`) exercises this exact chain against the synthetic 10-case fixture in CI — the same chain SHA-68 will replay against the Phase 6 corpus.

## CLI

```bash
PYTHONPATH=packages python -m eval.ablate \
    --gold        data/gold_standard/housing_v1.jsonl \
    --predictions hybrid=eval/predictions/hybrid.jsonl \
    --predictions rag_only=eval/predictions/rag_only.jsonl \
    --predictions kg_only=eval/predictions/kg_only.jsonl \
    --predictions llm_only=eval/predictions/llm_only.jsonl \
    --out eval/results/ablation_2026-05-01.json \
    --seed 42
```

Flags:

| Flag | Default | Purpose |
|---|---|---|
| `--gold PATH` | required | Gold-set JSONL |
| `--predictions MODE=PATH` | required (≥1, repeatable) | Per-mode predictions |
| `--out PATH` | stdout | Where to write the report |
| `--seed INT` | 42 | Bootstrap RNG seed (reproducibility) |
| `--n-resamples INT` | 1000 | Bootstrap resample count |
| `--no-bootstrap` | off | Skip bootstrap (point estimates only) |
| `--amount-threshold-pct FLOAT` | 0.20 | Tolerance for `amount_within_threshold` (0.20 = 20%) |

## Output shape

```json
{
  "n_cases": 10,
  "seed": 42,
  "n_resamples": 1000,
  "modes": [
    {
      "mode": "hybrid",
      "accuracy": {"point": 1.0, "lower_95": 1.0, "upper_95": 1.0, "n": 10, "n_resamples": 1000},
      "amount_threshold": {"point": 1.0, "lower_95": 1.0, "upper_95": 1.0, "n": 10, "n_resamples": 1000},
      "brier": {"point": 0.025, "lower_95": 0.025, "upper_95": 0.025, "n": 10, "n_resamples": 1000},
      "ece": {"point": 0.05, "lower_95": 0.05, "upper_95": 0.05, "n": 10, "n_resamples": 1000}
    }
    /* ...rag_only, kg_only, llm_only... */
  ],
  "gold_path": "...",
  "predictions_paths": {"hybrid": "...", ...},
  "computed_at": "2026-05-01T..."
}
```

## Worked example — synthetic 10-case corpus

The repo ships four synthetic per-mode prediction fixtures alongside the 10-case corpus (`packages/eval/tests/fixtures/`). They demonstrate the RQ1 ranking deterministically — no LLM calls, hand-crafted error patterns:

| Mode | Winner errors | Confidence |
|---|---|---|
| hybrid | 0% | 1.0 |
| rag_only | every 4th issue | 0.85 |
| kg_only | every 2nd issue | 0.7 |
| llm_only | always SPLIT | 0.5 |

Run:

```bash
PYTHONPATH=packages python -m eval.ablate \
    --gold        packages/eval/tests/fixtures/synthetic_corpus_10.jsonl \
    --predictions hybrid=packages/eval/tests/fixtures/predictions_synthetic_hybrid.jsonl \
    --predictions rag_only=packages/eval/tests/fixtures/predictions_synthetic_rag_only.jsonl \
    --predictions kg_only=packages/eval/tests/fixtures/predictions_synthetic_kg_only.jsonl \
    --predictions llm_only=packages/eval/tests/fixtures/predictions_synthetic_llm_only.jsonl \
    --no-bootstrap
```

Resulting point estimates:

| Mode | Accuracy | Amount within ±20% | Brier | ECE |
|---|---:|---:|---:|---:|
| hybrid | **1.00** | 1.00 | **0.025** | **0.05** |
| rag_only | 0.80 | 1.00 | 0.185 | 0.32 |
| kg_only | 0.50 | 1.00 | 0.306 | 0.52 |
| llm_only | 0.10 | 1.00 | 0.250 | 0.50 |

Two things worth noting:

1. **Brier ranks `kg_only` *worse* than `llm_only`.** That's because confidently-wrong (kg_only at 0.7 confidence on flipped winners) penalises Brier more than a coinflip baseline (llm_only at 0.5). It's a real methodological signal — a poorly-grounded but overconfident pipeline can score worse on calibration than one that just shrugs.
2. **`amount_threshold` is 1.0 across all modes** because the synthetic fixtures preserve the actual award amount even when flipping the winner. Real LLM outputs will move this metric — the synthetic fixtures don't try to model amount errors. They exist to demonstrate the pipeline, not to provide a thesis baseline.

## How "X significantly better than Y" gets decided

`summarise_dominance(a, b)` returns one of `a_dominates`, `b_dominates`, or `no_dominance` per metric. The rule is **non-overlapping bootstrap CIs**:

- For *higher-is-better* metrics (`accuracy`, `amount_threshold`):
  `a` dominates `b` if `a.lower_95 > b.upper_95`.
- For *lower-is-better* metrics (`brier`, `ece`):
  `a` dominates `b` if `a.upper_95 < b.lower_95`.

Overlap → `no_dominance`. The thesis claim "hybrid > RAG-only" lands only when the hybrid CI doesn't overlap the RAG-only CI.

This is conservative — formal pairwise hypothesis testing (e.g. paired bootstrap, McNemar's test) gives tighter answers — but CI-overlap is interpretable, robust to small n, and survives an examiner's "explain how you decided X is significantly better".

## Vocabulary mismatch — issue alignment caveat

The orchestrator's `DisputeIssue` enum (the issue vocabulary the prediction engine emits), the eval `ClaimType` enum (the stratification vocabulary), and the gold `claimed_amounts.issue` labels (free-text per-issue metric keys) are not identical. Phase 5b handles the deterministic parts:

- `eval.issue_alignment` maps clean enum pairs (`damage` ↔ `damages`, `deposit_protection` ↔ `deposit_non_protection`).
- `gold_case_to_case_file` records an unambiguous `ClaimType → claimed_amounts.issue` map when the pre-decision labels are one-to-one.
- `predict_all.py` applies that map before writing JSONL, so metrics join on the gold issue labels where the mapping is safe.

Ambiguous cases are deliberately left unmapped and score through the existing "missing prediction" path. That is conservative: it makes alignment loss visible instead of manufacturing a fake per-issue match.

## Reproducibility

- Determinism: `--seed 42` (default) — bootstrap CIs are byte-identical across runs.
- Fixtures: synthetic predictions regenerate from `_build_ablation_predictions.py`. A regression test (`test_ablation_fixtures.py`) locks the accuracy ranking.
- CI: the synthetic ablation runs as part of the eval test suite — no LLM dependency.

## Linear + cross-references

- This PR closes/advances **SHA-32** (ablation runner). The Phase 5 strategic-plan row in `.sisyphus/plans/track-a-plan.md` is updated.
- Predecessor: SHA-33 (PredictionMode flag), already on main.
- Successor: **SHA-68** (RQ1 ablation report). Once Phase 6 produces the real corpus, SHA-68 reads the JSON output from `eval.ablate` and renders the thesis table.
- Deferred follow-ups (own tickets):
  - `GoldCase → CaseFile` reconstructor (lossy mapping; needs Codex sparring)
  - Live runner script that loops `PredictionEngineV2.predict()` over real cases
  - Issue-vocabulary alignment between `DisputeIssue` and `ClaimType`

## Related docs

- [`methodology.md`](methodology.md) §Ablation methodology
- [`metrics.md`](metrics.md) — what each scalar means
- [`architecture.md`](architecture.md) — module dependency graph
- [`decision-log.md`](decision-log.md) — D-009 (bootstrap pair resampling), D-011 (Provenance model)
