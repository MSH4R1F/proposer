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
| 3. Annotation CLI + first 10 cases | SHA-28 | `scripts/eval/annotate.py`; `data/gold_standard/housing_v1.jsonl` (10 cases, manifest, OCR-confidence in metadata) | 10 cases validated; reviewer onboarding doc written; **two reviewers confirmed by Mohamed** (one primary, one for the double-annotated subset — see "Annotation reliability" below) |
| 4. Metrics package | SHA-30, SHA-31, SHA-29, SHA-97 | `accuracy.py`, `calibration.py`, `citations.py`, `ragas.py`, `uncertainty.py` + tests | `python -m eval.run --metric brier_score` runs against fixture and emits PNG reliability diagram with bootstrap 95% CI band; CI Brier-regression guard wired |
| 5. Ablation runner | SHA-32 | `packages/eval/run.py --mode {rag-only,kg-only,hybrid,llm-only}` + `scripts/eval/ablation.sh` | Ablation MD reproduces in <30 min on laptop, every metric reported as `(point, lower_95, upper_95, n)`. **Blocks on Track B SHA-33** — until `mode` flag lands, runner is stubbed against a fake `PredictionEngineV2` and tests pass against the stub |
| 6. Annotation push to 50 cases | SHA-28 DoD | 50 cases in jsonl; ≥5 (10%) blind double-annotated; Cohen's kappa ≥0.8 reported per claim type; reviewer sign-off and adjudication log recorded in `docs/eval/reviewer-log.md` | DoD met; hand-off note opened on SHA-68 |

**Stratification target** (rechecked at every commit to the jsonl): ≥5 cases where each `t in claim_types` appears (per SHA-92, multi-type cases count toward each of their types); 30/70 region/case-size split; PILOT temporal split (no shuffle).

## Annotation reliability (SHA-96 — Codex finding [7])

Single-reviewer sign-off is not defensible against an examiner attacking gold-set subjectivity. Required protocol for Phase 3 + Phase 6:

- **Blind double annotation** of ≥10% of the corpus (≥5 of the 50-case DoD). Reviewer B sees only the source PDF + schema; not Reviewer A's labels.
- **Adjudication log** at `docs/eval/reviewer-log.md`: every disagreement gets a row recording the disputed field, both reviewers' choices, the resolution, and the rationale. Final label adopted only after adjudication.
- **Cohen's kappa target** ≥0.8 reported per `claim_type` (after SHA-92, per *each* type since cases are multi-typed). Computed in Phase 6 by `scripts/eval/agreement.py`. Sub-0.8 kappa for any type triggers a guideline-revision loop before the corpus is declared DoD-complete.
- **Staffing escalation:** this requires a second reviewer. The SHA-28 comment to @Mohamed has been upgraded from "paralegal pair-up" to "primary reviewer + second reviewer for the double-annotated subset."

## Statistical reporting (SHA-97 — Codex finding [8])

The interim report commits to `accuracy >70%`, `Brier <0.20`, `hallucination <2%` as point estimates. With n=50 those numbers are unstable; an examiner will attack any thesis claim that doesn't survive resampling. Required for every metric the harness ships:

- **Bootstrap 95% CIs** with n=1000 resamples, computed at the case level (not the issue level — issues within a case are not iid). Per-stratum and overall.
- **Minimum effective n per cell** of the stratification table — define a "thesis-defensible" floor (e.g. n ≥ 8 per cell) below which point estimates are reported but no thesis claim is made.
- **Report shape:** every metric runner emits `(point, lower_95, upper_95, n)` rather than a bare scalar.
- **Claim-survival audit:** a thesis claim only "lands" if its lower CI bound clears the headline target (`accuracy_lower_95 > 0.70`, `brier_upper_95 < 0.20`, `unsupported_lower_95 < 0.02`). `scripts/eval/thesis_audit.py` lists which claims survive their CIs at every gold-set update; the audit output is committed alongside the gold set.
- **Implementation:** `packages/eval/metrics/uncertainty.py` provides `bootstrap_ci(metric_fn, cases, n_resamples=1000, seed=...)`. Tests cover deterministic seed, length invariance, and lower≤point≤upper monotonicity.

## Test discipline

- TDD per `superpowers:test-driven-development`. Tests precede implementation **including** for schema validators (the schema is load-bearing for every downstream metric — getting it wrong corrupts every result).
- New `packages/eval/` package: ≥80% coverage gate (committed to `pyproject.toml` once package skeleton lands).
- Frozen-fixture tests: 3 tiny synthetic gold cases checked into `tests/eval/fixtures/` so metric tests don't depend on the real annotated set.

## Open dependencies / risks (with mitigations)

1. **Two reviewers required** (escalated from "one paralegal" after SHA-96) — *blocks DoD, not implementation*. Mitigation: develop schema/metrics/runner against the synthetic fixtures; flip to real annotation only once both reviewers are paired. **Surfaced to @Mohamed in the SHA-28 comment.**
2. **SHA-33 (Track B) not yet landed** — `PredictionEngineV2` has no `mode` flag. Mitigation: phase 5 is built against a stub interface (`class PredictionMode(StrEnum); class PredictorProtocol(Protocol)`) and integration test is skipped (`pytest.mark.skipif(...not mode_flag_available)`) until SHA-33 merges. Linear comment opened on SHA-33 specifying the exact protocol Track A needs.
3. **OCR noise in tribunal PDFs** — Mitigation: every `GoldCase` carries `ocr_confidence: float | None` and `source_pdf_sha256: str`; annotation CLI flags low-confidence spans for human review.
4. **Temporal-split leakage** — Mitigation: `dataset.audit()` rejects load if any train case has an authority in `cited_authorities` with `cited_date > 2022-12-31` (SHA-90 wires the data needed); runs in CI.
5. **Annotation cost (the real bottleneck)** — Plan stages 10 → 50 (DoD) → 100. Phase 6 explicitly assumes two reviewers for the double-annotated subset; without them we ship at 50 single-annotated and the kappa metric in DoD goes unmet.
6. **Schema mutability window** (per SHA-95) — `v1` is mutable until pilot batch (10 cases) ships AND every HIGH Codex finding is closed. Phase 3 must not accept reviewer sign-off before that window closes, otherwise we'll need a `v2` migration earlier than necessary.
7. **Atomic claim units missing** (SHA-94, deferred) — `unsupported_claim_rate` (Phase 4 / SHA-31) needs schema redesign for atomic claim → support links. Brainstorming session must happen before Phase 4 starts; otherwise the metric ships against a workaround and the thesis claim is weaker than promised.

## Codex sparring checkpoints (per launch prompt)

- After phase 1 (schema): "what failure modes will this gold-case schema have under noisy real-world tribunal text?" → `.sisyphus/codex/sha-28-schema-2026-04-27.md`
- After phase 4 (Brier numbers in): "what would an examiner attack first?" → `.sisyphus/codex/sha-30-calibration-<date>.md`

## Definition of done (Track A overall, lifts from SHA-14 epic verbatim, augmented post-Codex)

- [ ] `packages/eval/` runnable via `python -m eval.run --domain housing`
- [ ] Gold set committed at `data/gold_standard/housing_v1.jsonl` (versioned, ≥50 cases, two-reviewer sign-off recorded; ≥5 cases double-annotated; Cohen's kappa ≥0.8 per `claim_type` reported)
- [ ] Brier + ECE + reliability PNG produced with bootstrap 95% CI; CI fails on >0.05 Brier regression vs main
- [ ] Hallucination unsupported-claim-rate metric reported per gold case with bootstrap CI (target measurable; lands as a thesis claim only if `unsupported_lower_95 < 0.02`)
- [ ] RAGAS faithfulness / context precision-recall / answer relevance reported nightly to `eval/results/ragas_<date>.json`
- [ ] Ablation table reproduces in <30 min on laptop, four modes, every metric as `(point, lower_95, upper_95, n)`
- [ ] `scripts/eval/thesis_audit.py` runs at every gold-set update; result committed; only CI-surviving claims are made in the thesis
- [ ] Hand-off comment written on SHA-68 (RQ1 ablation report) so Track B can pick up the report writing
