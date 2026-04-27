# Track A — Eval Data & Gold Standard: Implementation Plan

**Author:** Track A window (this worktree)
**Date:** 2026-04-27
**Branch:** `feature/sha-28-build-gold-standard-test-set`
**Linear epic:** [SHA-14](https://linear.app/sharifbuilders/issue/SHA-14) — Evaluation Infrastructure & Gold Standard
**Critical-path child:** [SHA-28](https://linear.app/sharifbuilders/issue/SHA-28)

> 1-page strategic plan as required by the Track A launch prompt. Each phase below will get its own bite-sized TDD plan (per `superpowers:writing-plans`) at `docs/superpowers/plans/2026-04-27-gold-set-<phase>.md` immediately before execution. Numbered phases run sequentially; phase 4 unblocks per-metric parallelism.

## Goal

Stand up `packages/eval/` and ship `data/gold_standard/housing_v1.jsonl` so every Mohamed thesis claim (accuracy >70%, Brier <0.20, hallucination <2%, hybrid > RAG-only / KG-only) becomes a reproducible number, not a slogan.

## Architecture (one diagram)

```
data/gold_standard/housing_v1.jsonl   ← versioned, schema-validated source of truth
        │
        ├─→ packages/eval/schema.py           (Pydantic GoldCase, version field, OCR meta)
        ├─→ packages/eval/dataset.py          (load/validate/iter, temporal-split helpers)
        ├─→ packages/eval/metrics/
        │     accuracy.py, calibration.py (Brier+ECE+reliability),
        │     citations.py (NLI entailment), ragas.py (faithfulness etc.)
        └─→ packages/eval/run.py              (CLI: python -m eval.run --metric X --mode Y)
                │
                └─→ scripts/eval/ablation.sh  (calls run.py with all 4 modes, writes md)
                       depends on Track B SHA-33 (PredictionEngineV2 mode flag)
```

Annotation tooling lives in `scripts/eval/annotate.py` (one-case-at-a-time CLI; reviewer hand-off is JSON patch).

## Phase plan

| Phase | Linear | Output | Exit criterion |
|---|---|---|---|
| 1. Gold-case schema (Pydantic) | SHA-28 | `packages/eval/schema.py` + tests + `docs/eval/gold-schema.md` | Schema round-trips a hand-built fixture; **Codex schema sparring complete** |
| 2. Dataset loader + temporal-split helper | SHA-28 | `packages/eval/dataset.py` + tests | `dataset.load("housing_v1")` returns iterator; `dataset.train()`/`dataset.test()` enforce 2019–22 / 2023–24 with date-leakage audit |
| 3. Annotation CLI + first 10 cases | SHA-28 | `scripts/eval/annotate.py`; `data/gold_standard/housing_v1.jsonl` (10 cases, manifest, OCR-confidence in metadata) | 10 cases validated; reviewer onboarding doc written; **paralegal pair-up confirmed by Mohamed** |
| 4. Metrics package | SHA-30, SHA-31, SHA-29 | `accuracy.py`, `calibration.py`, `citations.py`, `ragas.py` + tests | `python -m eval.run --metric brier_score` runs against fixture and emits PNG reliability diagram; CI Brier-regression guard wired |
| 5. Ablation runner | SHA-32 | `packages/eval/run.py --mode {rag-only,kg-only,hybrid,llm-only}` + `scripts/eval/ablation.sh` | Ablation MD reproduces in <30 min on laptop. **Blocks on Track B SHA-33** — until `mode` flag lands, runner is stubbed against a fake `PredictionEngineV2` and tests pass against the stub |
| 6. Annotation push to 50 cases | SHA-28 DoD | 50 cases in jsonl, paralegal sign-off recorded in `docs/eval/reviewer-log.md` | DoD met; hand-off note opened on SHA-68 |

**Stratification target** (rechecked at every commit to the jsonl): ≥5 cases per claim type (cleaning, damages, deposit-non-protection, disrepair, end-of-tenancy); 30/70 region/case-size split; PILOT temporal split (no shuffle).

## Test discipline

- TDD per `superpowers:test-driven-development`. Tests precede implementation **including** for schema validators (the schema is load-bearing for every downstream metric — getting it wrong corrupts every result).
- New `packages/eval/` package: ≥80% coverage gate (committed to `pyproject.toml` once package skeleton lands).
- Frozen-fixture tests: 3 tiny synthetic gold cases checked into `tests/eval/fixtures/` so metric tests don't depend on the real annotated set.

## Open dependencies / risks (with mitigations)

1. **Paralegal reviewer assignment** — *blocks DoD, not implementation*. Mitigation: develop schema/metrics/runner against the synthetic fixture; flip to real annotation only once reviewer is paired. **Surfaced to @Mohamed in the SHA-28 comment that links this plan.**
2. **SHA-33 (Track B) not yet landed** — `PredictionEngineV2` has no `mode` flag. Mitigation: phase 5 is built against a stub interface (`class PredictionMode(StrEnum); class PredictorProtocol(Protocol)`) and integration test is skipped (`pytest.mark.skipif(...not mode_flag_available)`) until SHA-33 merges. Linear comment opened on SHA-33 specifying the exact protocol Track A needs.
3. **OCR noise in tribunal PDFs** — Mitigation: every `GoldCase` carries `ocr_confidence: float | None` and `source_pdf_sha256: str`; annotation CLI flags low-confidence spans for human review.
4. **Temporal-split leakage** — Mitigation: `dataset.audit()` rejects load if any train case cites an authority dated after 2022-12-31; runs in CI.
5. **Annotation cost (the real bottleneck)** — Plan stages 10 → 50 (DoD) → 100. Phase 6 explicitly assumes a paralegal partner; without one we ship at 50 not 100.

## Codex sparring checkpoints (per launch prompt)

- After phase 1 (schema): "what failure modes will this gold-case schema have under noisy real-world tribunal text?" → `.sisyphus/codex/sha-28-schema-2026-04-27.md`
- After phase 4 (Brier numbers in): "what would an examiner attack first?" → `.sisyphus/codex/sha-30-calibration-<date>.md`

## Definition of done (Track A overall, lifts from SHA-14 epic verbatim)

- [ ] `packages/eval/` runnable via `python -m eval.run --domain housing`
- [ ] Gold set committed at `data/gold_standard/housing_v1.jsonl` (versioned, ≥50 cases, paralegal signed off)
- [ ] Brier + ECE + reliability PNG produced; CI fails on >0.05 Brier regression vs main
- [ ] Hallucination unsupported-claim-rate metric reported per gold case (target measurable, not necessarily <2% yet)
- [ ] RAGAS faithfulness / context precision-recall / answer relevance reported nightly to `eval/results/ragas_<date>.json`
- [ ] Ablation table reproduces in <30 min on laptop, four modes
- [ ] Hand-off comment written on SHA-68 (RQ1 ablation report) so Track B can pick up the report writing
