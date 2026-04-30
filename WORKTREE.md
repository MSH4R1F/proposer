# WORKTREE — SHA-14: Evaluation Infrastructure & Gold Standard

## Owner
This Claude Code window (Track A — Eval Data). Branch: `feature/sha-28-build-gold-standard-test-set`.

## Linear
- Epic: SHA-14 — Evaluation Infrastructure & Gold Standard
- Children in flight (sequence):
  1. **SHA-28** — Gold standard test set (50–100 cases, 2019–22 train / 2023–24 test)
  2. **SHA-30** — Brier / ECE calibration plots (depends on SHA-28)
  3. **SHA-31** — NLI hallucination audit
  4. **SHA-29** — RAGAS metrics integration
  5. **SHA-32** — Ablation harness (RAG-only / KG-only / hybrid / llm-only) — depends on Track B SHA-33
  6. Hand off to Track B for **SHA-68** RQ1 ablation report
- DoD (verbatim from epic SHA-14):
  - `packages/eval/` package exists, runnable via `python -m eval.run --domain housing`
  - Gold set committed at `data/gold_standard/housing_v1.jsonl` (versioned)
  - Nightly CI publishes accuracy/Brier/hallucination dashboard
  - Ablation table reproduces in <30 min on a single laptop
- DoD (SHA-28, the critical-path child):
  - Schema doc + 50 cases minimum committed
  - Reviewer signs off (paralegal/law student)
  - Stratification: ≥5 cases per claim type (cleaning, damages, deposit-non-protection, disrepair, end-of-tenancy)
  - 30/70 region / case-size split
  - Temporal split: 2019–22 train, 2023–24 test (PILOT methodology — no shuffle)

## Files allowed
- `data/gold_standard/**` (new)
- `packages/eval/**` (new)
- `scripts/eval/**` (new)
- `tests/eval/**` (new)
- `docs/eval/*.md` (drafted here, indexed by Window 1 Research & Docs)
- `.sisyphus/evidence/eval/**`
- `.sisyphus/plans/track-a-*.md`
- `.sisyphus/codex/sha-*-track-a-*.md`
- This worktree's `WORKTREE.md`

## Files forbidden (read-only)
- `apps/**`
- `packages/rag_engine/**` (Track C)
- `packages/kg_builder/**` (Track B)
- `packages/llm_orchestrator/pipeline/prediction_engine_v2.py` (Track B)
- Any other window's worktree

If a change is needed in a forbidden file, leave a Linear comment on the affected ticket — do not edit.

## Sibling windows (do not edit their files)
- Track Research & Docs: `docs/prompts/research-and-docs.md`
- Track B — KG wiring: SHA-33 — `worktrees/sha-33-kg-wiring/` (SHA-32 ablation runner depends on SHA-33's `mode` flag in PredictionEngineV2)
- Track C — RAG quick wins: SHA-22 — `worktrees/sha-22-contextual/`

## Codex sparring schedule
- Pre-implementation (schema phase): "what failure modes will the gold-case schema have under noisy real-world tribunal text?" → `.sisyphus/codex/sha-28-schema-<date>.md` — invoked? **no**
- Pre-publish (after Brier numbers): "what would an examiner attack first?" — invoked? **no**

## Open dependencies / blockers
- **Paralegal reviewer assignment** (Mohamed) — needed for SHA-28 sign-off. Cannot reach 50-case DoD without it.
- **SHA-33** (Track B) — must expose `mode` flag in `PredictionEngineV2`. SHA-32 ablation runner blocks on this.

## Status
- 2026-04-27: Worktree created from `main` at commit `ac212fd`. Reading launch prompt + Linear DoDs. Plan next.
