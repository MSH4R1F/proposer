# Evaluation Harness — Documentation Index

> **For thesis writers:** start with [methodology.md](methodology.md) for the chapter narrative, then [decision-log.md](decision-log.md) for "why did you do X?" answers, then [architecture.md](architecture.md) for the diagram. Implementation details are in the per-component docs below.

The evaluation harness is the part of Proposer that proves the thesis. Its job: make every claim in the interim report — accuracy >70%, Brier <0.20, hallucination <2%, hybrid > RAG-only / KG-only — empirically testable, reproducible, and defensible against an examiner.

This index maps every doc in `docs/eval/` to its audience and purpose.

## For the thesis writer

| Doc | Read this when… |
|---|---|
| [`methodology.md`](methodology.md) | You're writing the "Evaluation methodology" chapter. Has the citations, the design rationale, the comparison to prior work. |
| [`decision-log.md`](decision-log.md) | You're prepping the viva. Records every non-obvious choice, what was rejected, and why. Codex sparring outcomes folded in. |
| [`architecture.md`](architecture.md) | You need a diagram for the thesis or for a slide deck. Data flow, module ownership, dependency graph. |
| `../../packages/eval/tests/fixtures/synthetic_corpus_10.jsonl` | You need example data to illustrate the pipeline. |
| `../../.sisyphus/codex/sha-28-schema-2026-04-27.md` | You want to discuss the failure-mode analysis we ran on the schema. Verbatim Codex review + 12 findings. |

## For someone using the harness

| Doc | What it covers |
|---|---|
| [`gold-schema.md`](gold-schema.md) | Field-by-field schema reference. Every cross-field invariant (INV-1..INV-10) with rationale. |
| [`dataset.md`](dataset.md) | The `eval.dataset` API: `load`, `train`, `test`, `audit`. CLI usage. Lenient/strict mode pattern. |
| [`metrics.md`](metrics.md) | Per-metric definitions, the bootstrap CI shape, the thesis-claim survival rule, CLI worked example. |
| [`reviewer-guide.md`](reviewer-guide.md) | Paralegal onboarding. TL;DR loop, field-by-field, common mistakes, adjudication workflow. |
| [`reviewer-log.md`](reviewer-log.md) | Adjudication log template. One row per double-annotation disagreement. |

## For someone reproducing the work

End-to-end reproducibility:

```bash
# 1. Audit the gold set
PYTHONPATH=packages python -m eval.dataset audit data/gold_standard/housing_v1.jsonl --strict --evidence

# 2. Run a metric with bootstrap CIs
PYTHONPATH=packages python -m eval.run --metric accuracy \
  --gold data/gold_standard/housing_v1.jsonl \
  --predictions eval/predictions/<run-id>.jsonl \
  --seed 42 \
  --out eval/results/accuracy_$(date +%F).json

# 3. Same for Brier, ECE
PYTHONPATH=packages python -m eval.run --metric brier --gold ... --predictions ... --seed 42 --out ...
PYTHONPATH=packages python -m eval.run --metric ece   --gold ... --predictions ... --seed 42 --out ...
```

Determinism: every CI is reproducible with `--seed`. Reproducibility evidence (per-phase coverage, audit JSON) lives at `.sisyphus/evidence/eval/`.

## Phase status

| Phase | Status | Linear | What |
|---|---|---|---|
| 1 — Schema (`packages/eval/schema.py`) | **Done** ([PR #7](https://github.com/MSH4R1F/proposer/pull/7)) | SHA-90/91/92/93/95/98/99/100 | `GoldCase` Pydantic model, 10 cross-field invariants |
| 2 — Dataset loader (`packages/eval/dataset.py`) | **Done** ([PR #7](https://github.com/MSH4R1F/proposer/pull/7)) | SHA-101 | `load`/`train`/`test`/`audit` + CLI |
| 3 — Annotation CLI + reviewer onboarding | **Done** ([PR #8](https://github.com/MSH4R1F/proposer/pull/8)) | SHA-103 | `scripts/eval/annotate.py`, reviewer guide, synthetic corpus |
| 4a — Accuracy + calibration + bootstrap CI | **Done** ([PR #8](https://github.com/MSH4R1F/proposer/pull/8)) | SHA-104, SHA-30, SHA-97 (partial) | `packages/eval/metrics/`, `eval.run` CLI |
| 4b — NLI hallucination + RAGAS | Deferred | SHA-31, SHA-29 | Heavy ML deps; depends on SHA-94 schema |
| 5 — Ablation runner | Pending | SHA-32 | Depends on Track B SHA-33 (KG mode flag — landed) |
| 6 — Push to 50 cases + Cohen's κ | Pending | SHA-28 DoD | Depends on reviewer assignment (SHA-96) |

## Source of truth pointers

- **Pydantic schema:** `packages/eval/schema.py`
- **Loader + audit:** `packages/eval/dataset.py`
- **Metrics:** `packages/eval/metrics/{accuracy,calibration,uncertainty,types}.py`
- **CLI orchestrator:** `packages/eval/run.py`
- **Annotation CLI:** `scripts/eval/annotate.py`
- **Tests:** `packages/eval/tests/`
- **Synthetic fixtures:** `packages/eval/tests/fixtures/`
- **Production gold set:** `data/gold_standard/housing_v1.jsonl` (lands when Phase 6 annotation completes)
- **Strategic track plan:** `.sisyphus/plans/track-a-plan.md`
- **TDD plans (per phase):** `docs/superpowers/plans/2026-04-{27,28,29}-gold-set-*.md`
- **Codex sparring record:** `.sisyphus/codex/sha-28-schema-2026-04-27.md`
- **Coverage evidence:** `.sisyphus/evidence/eval/phase{1,2,4a}-*-coverage.txt`

## Glossary (one-liners)

| Term | Meaning |
|---|---|
| **Gold standard** | The 50–100 manually-annotated cases that downstream metrics are scored against. |
| **PILOT split** | Train on 2019–2022, test on 2023–2024 (no shuffle). Tests temporal generalisation. |
| **Apportioned outcome** | A tribunal decision that breaks the award down per issue. The default schema path. |
| **Unapportioned outcome** | A tribunal decision that gives one global figure with no per-issue breakdown. Schema supports it via `unapportioned_reason`. |
| **Stratification floor** | Minimum cases per `claim_type` (5). Multi-type cases count toward each of their types. |
| **Temporal leakage** | A train case citing an authority dated after the train-window cutoff. Inflates accuracy if not caught. |
| **Brier score** | Mean squared error of `(P(landlord wins) - actual_landlord_won)`. Lower is better; 0.25 = coin-flip. |
| **ECE** | Expected Calibration Error: weighted mean of `|bin_accuracy - bin_confidence|` across confidence bins. |
| **Reliability diagram** | Bar plot of bin accuracy vs confidence; y=x diagonal = perfect calibration. |
| **Bootstrap 95% CI** | Resample (gold[i], prediction[i]) PAIRS with replacement n=1000 times; report 2.5/97.5 percentiles. |
| **Thesis-claim survival** | A claim "lands" only if its lower CI bound clears the headline target (e.g. `accuracy_lower_95 > 0.70`). |
| **Provenance** | Structured `(page, paragraph, optional text_span)` tuple replacing free-text `paragraph_ref`. |
| **Codex sparring** | A pre-publish review session with Codex to surface schema failure modes before annotation begins. |
| **Cohen's κ** | Inter-annotator agreement metric; ≥0.8 target per claim type. |

For longer definitions, see [methodology.md](methodology.md) §3 (Terminology).
