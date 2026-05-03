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
| 3. **LLM-assisted labeling pipeline + adjudication CLI + first 10 cases** (rewritten 2026-05-02 — see decision-log D-019) | SHA-28 / SHA-TBD | `packages/eval/auto_label/**`, `packages/llm_orchestrator/clients/labeler_factory.py`, `scripts/eval/auto_label.py`, `scripts/eval/adjudicate.py`, first 10 rows in `data/gold_standard/housing_v1.jsonl` with `labeling_provenance` populated; reviewer-guide rewritten as adjudicator-only flow | 10 cases produced end-to-end through the dual-LLM + auto-grounder + human-adjudication pipeline; every row passes `assert_real_gold_appendable`; MandatoryReviewSet completed; per-case run artifacts under `data/eval_artifacts/labeling/<run_id>/<case_id>.json`; **only one human (adjudicator) required**, paralegal-pair staffing dependency removed |
| 4. Metrics package | SHA-30, SHA-31, SHA-29, SHA-97 | `accuracy.py`, `calibration.py`, `citations.py`, `ragas.py`, `uncertainty.py` + tests | `python -m eval.run --metric brier_score` runs against fixture and emits PNG reliability diagram with bootstrap 95% CI band; CI Brier-regression guard wired |
| 5. Ablation runner | SHA-32 | `packages/eval/{adapter,compare,ablate}.py` + synthetic per-mode fixtures + `docs/eval/ablation.md` | **Done** — `python -m eval.ablate --predictions mode=path…` produces a `ComparisonReport` JSON with bootstrap CIs for every mode. Synthetic fixtures demonstrate the RQ1 ranking deterministically; live LLM runner deferred to follow-up PR (blocks on Phase 6 real corpus + GoldCase→CaseFile reconstruction) |
| 6. **Push to 50 cases via LLM-assisted pipeline + 10–20-case human-only anchor set** (rewritten 2026-05-02) | SHA-28 DoD | 50 cases in `housing_v1.jsonl`; MandatoryReviewSet completed for every row; 10% deterministic random audit of agreed cells; stratified 10–20-case human-only anchor set labeled from scratch (no LLM seed); `LabelingProvenance` captures `inter_model_agreement_rate`, `audit_flip_rate`, `mandatory_review_flip_rate`; metrics reported per anchor / LLM-assisted / combined splits; combined-corpus calibration claim only when anchor divergence is below the pre-registered threshold (Brier delta ≤ 0.05 and no systematic winner-flip pattern) | DoD met; thesis-claim-survival audit run; hand-off note opened on SHA-68 |

**Stratification target** (rechecked at every commit to the jsonl): ≥5 cases where each `t in claim_types` appears (per SHA-92, multi-type cases count toward each of their types); 30/70 region/case-size split; PILOT temporal split (no shuffle).

## Annotation reliability under LLM-assisted labeling (rewritten 2026-05-02 — supersedes SHA-96)

The original two-paralegal protocol (Codex finding [7]) is dropped: paralegal staffing was not deliverable on Mohamed's working timetable, and "two-paralegal Cohen's κ" is not the only defensible reliability story. The LLM-assisted pipeline is documented in full at `.sisyphus/codex/sha-tbd-llm-labeling-2026-05-02.md` (Codex-revised). Required protocol for Phase 3 + Phase 6:

- **Dual-LLM extraction** with explicit `LabelerModelSpec` configs (one Anthropic, one OpenAI) — proves provider independence per Codex finding [4]. The role-keyed `get_llm_client(LLMRole.EXTRACTION)` is **not** used for labeling; the new `packages/llm_orchestrator/clients/labeler_factory.py` constructs both clients directly.
- **Auto-grounder** rejects every cell that cannot be resolved to a basis span in the source PDF (canonicalised quote match, BAILII authority lookup, UK statutes lookup, INV-1..INV-10), so the agreed-cell set is defensible by construction, not just by model agreement.
- **MandatoryReviewSet** — the human adjudicator confirms every metric-critical cell (`facts`, `disputed_amount_gbp`, `claim_types`, `matter_type`, `ground_truth_outcome.{overall_winner,total_awarded_gbp,per_issue.*,unapportioned_reason}`) on **every real gold row**, regardless of A/B agreement. This is the firewall against "LLMs agreed therefore truth."
- **DisagreementSet** — every cell where A/B disagree, either is ungrounded, an invariant fails, a basis span is missing, or null/non-null differs is routed to the same adjudicator. Field-path-level granularity (`evidence[key].kind`, `per_issue[issue=damages].winner`) so list disagreements are not hidden inside list equality.
- **10% agreed-cell audit overlay** — a deterministic 10% random sample of agreed cells is also surfaced to the adjudicator. The resulting `audit_flip_rate` is recorded in `LabelingProvenance` and is the single best operational signal that the LLM pair is biased.
- **Human-only anchor set** — a stratified 10–20-case subset is labeled from scratch by the adjudicator without seeing either LLM output. Metrics are reported per anchor / LLM-assisted / combined splits; a combined-corpus calibration claim only lands if anchor divergence is below the pre-registered threshold.
- **`inter_model_agreement_rate`** is **NOT Cohen's κ** and must not be reported as one. It is raw operational telemetry only. The defensibility metrics are: mandatory-review flip rate, 10% audit flip rate, anchor-set divergence, and adjudication rate by field path.
- **Adjudication log** at `docs/eval/reviewer-log.md` — one row per disputed `(case, field_path)` cell; rationale required.
- **Real-gold append gate** at `packages/eval/auto_label/append_gate.py` refuses any row with: missing `labeling_provenance`, `negative_kind` set, missing `target_source_id` or manifest fields, incomplete MandatoryReviewSet coverage, or missing/mismatched run artifact hashes. Negative-set fixtures (`data/eval/negative_sets/*.jsonl`) never go through this gate.
- **Staffing**: one trained adjudicator (paralegal or law student). Two-paralegal staffing is no longer required.

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

1. **Adjudicator availability** (replaces "two reviewers required" — superseded by D-019) — one trained adjudicator (paralegal or law student) walks the MandatoryReviewSet + DisagreementSet + 10% audit overlay for every real gold row, and labels the 10–20-case anchor set from scratch. Mitigation: pipeline lands fully end-to-end without the adjudicator (Phases 1–11); adjudicator is needed only at append time, not implementation time.
2. **Circularity attack on LLM-labeled gold** (NEW; see D-019 and `.sisyphus/codex/sha-tbd-llm-labeling-2026-05-02.md`) — examiner: "you used LLMs to label the gold set used to evaluate your LLM predictor." Mitigation stack: deterministic auto-grounder + MandatoryReviewSet + 10–20-case human-only anchor set + split-metric reporting + `inter_model_agreement_rate` reported as raw telemetry not as κ. A combined-corpus calibration claim is blocked when anchor divergence exceeds the pre-registered threshold (Brier delta > 0.05 or systematic winner-flip).
3. **SHA-33 (Track B) not yet landed** — `PredictionEngineV2` has no `mode` flag. Mitigation: phase 5 is built against a stub interface (`class PredictionMode(StrEnum); class PredictorProtocol(Protocol)`) and integration test is skipped (`pytest.mark.skipif(...not mode_flag_available)`) until SHA-33 merges. Linear comment opened on SHA-33 specifying the exact protocol Track A needs.
4. **OCR noise in tribunal PDFs** — Mitigation: every `GoldCase` carries `ocr_confidence: float | None` and `source_pdf_sha256: str`; LLM-assisted labeling CLI surfaces low-confidence spans to the adjudicator; the auto-grounder rejects ungrounded cells.
5. **Temporal-split leakage** — Mitigation: `dataset.audit()` rejects load if any train case has an authority in `cited_authorities` with `cited_date > 2022-12-31` (SHA-90 wires the data needed); runs in CI.
6. **Schema mutability window** (per SHA-95) — `v1` is mutable until pilot batch (10 cases) ships AND every HIGH Codex finding is closed. Phase 3 must not accept rows into `housing_v1.jsonl` before that window closes, otherwise we'll need a `v2` migration earlier than necessary.
7. **Atomic claim units missing** (SHA-94, deferred) — `unsupported_claim_rate` (Phase 4 / SHA-31) needs schema redesign for atomic claim → support links. Brainstorming session must happen before Phase 4 starts; otherwise the metric ships against a workaround and the thesis claim is weaker than promised.
8. **Labeler-model retirement** (NEW) — Mitigation: published gold rows are reproducible from frozen run artifacts (`data/eval_artifacts/labeling/<run_id>/<case_id>.json`) carrying raw model outputs, prompt + schema hashes, OCR engine/version, canonicalizer version, grounder version, and authority/statute index hashes. Live API replays are not required.

## Codex sparring checkpoints (per launch prompt)

- After phase 1 (schema): "what failure modes will this gold-case schema have under noisy real-world tribunal text?" → `.sisyphus/codex/sha-28-schema-2026-04-27.md`
- After labeling-pipeline draft (2026-05-02): "what attacks survive a dual-LLM + auto-grounder + human-anchor design?" → `.sisyphus/codex/sha-tbd-llm-labeling-2026-05-02.md` (revised draft folds in the 8 P1/P2 findings)
- After phase 4 (Brier numbers in): "what would an examiner attack first?" → `.sisyphus/codex/sha-30-calibration-<date>.md`

## Definition of done (Track A overall, lifts from SHA-14 epic verbatim, augmented post-Codex)

- [ ] `packages/eval/` runnable via `python -m eval.run --domain housing`
- [ ] Gold set committed at `data/gold_standard/housing_v1.jsonl` (versioned, ≥50 cases, every row produced by the LLM-assisted pipeline with `labeling_provenance` populated, MandatoryReviewSet completed, 10% audit-overlay flip rate recorded, 10–20-case human-only anchor set labeled, anchor/LLM-assisted/combined metrics reported separately)
- [ ] Brier + ECE + reliability PNG produced with bootstrap 95% CI; CI fails on >0.05 Brier regression vs main
- [ ] Hallucination unsupported-claim-rate metric reported per gold case with bootstrap CI (target measurable; lands as a thesis claim only if `unsupported_lower_95 < 0.02`)
- [ ] RAGAS faithfulness / context precision-recall / answer relevance reported nightly to `eval/results/ragas_<date>.json`
- [ ] Ablation table reproduces in <30 min on laptop, four modes, every metric as `(point, lower_95, upper_95, n)`
- [ ] `scripts/eval/thesis_audit.py` runs at every gold-set update; result committed; only CI-surviving claims are made in the thesis
- [ ] Hand-off comment written on SHA-68 (RQ1 ablation report) so Track B can pick up the report writing
