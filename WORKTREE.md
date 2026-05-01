# WORKTREE — SHA-32: Ablation Runner

## Owner
This Claude Code window (Track A — Eval Data, Phase 5). Branch: `feature/sha-32-ablation-runner` off `main` at `1b6248b`.

## Linear
- Epic: SHA-14 — Evaluation Infrastructure & Gold Standard
- Active child: **SHA-32** — Ablation harness (RAG-only / KG-only / hybrid / llm-only)
- Predecessors (already shipped on main):
  - SHA-28 / SHA-90–93 / SHA-95 / SHA-98–100 — gold-case schema (Phase 1)
  - SHA-101 — dataset loader + audit (Phase 2)
  - SHA-103 — annotation CLI + reviewer guide + 10-case fixture (Phase 3)
  - SHA-30 / SHA-97 — accuracy + calibration + bootstrap CI metrics (Phase 4a)
- Successor: SHA-68 — RQ1 ablation report (consumes the artifacts this PR produces)
- SHA-33 (Track B PredictionMode flag) is **landed on main** — unblocks this work.

## Scope cut (one PR)
**In:**
- `eval.adapter`: `PredictionResult` → `eval.metrics.types.Prediction` adapter (pure, unit-tested)
- `eval.compare`: gold + dict[mode→predictions] → ranked comparison report with bootstrap CIs (pure, unit-tested)
- `python -m eval.ablate` CLI: subprocess-tested against synthetic fixtures
- 4 synthetic per-mode prediction JSONLs against the existing 10-case corpus, demonstrating hybrid > rag > kg > llm
- `docs/eval/ablation.md` documenting methodology + CLI + worked example

**Out (deferred to follow-up PR, blocked on Phase 6 real corpus):**
- Live runner script that loops `PredictionEngineV2.predict()` over real cases
- `GoldCase` → `CaseFile` constructor (lossy, deserves its own PR + Codex sparring)

## Files allowed
- `packages/eval/**` (new modules: adapter.py, compare.py, ablate.py)
- `packages/eval/tests/**`
- `packages/eval/tests/fixtures/**` (synthetic per-mode prediction JSONLs)
- `docs/eval/ablation.md` (new)
- `docs/eval/README.md` (update phase status table)
- `.sisyphus/evidence/eval/phase5-*` (force-add)
- `.sisyphus/plans/track-a-plan.md` (update Phase 5 row)
- This `WORKTREE.md`

## Files forbidden (read-only — Track B / production)
- `packages/llm_orchestrator/**`
- `packages/rag_engine/**`
- `packages/kg_builder/**`
- `apps/**`
- Any other worktree

If a change is needed in a forbidden file, leave a Linear comment on the affected ticket — do not edit.

## Sibling windows
- Track B — KG wiring (SHA-33 landed)
- Track C — RAG quick wins
- Track Research & Docs — thesis Implementation chapter

## Codex sparring schedule
- Pre-publish (after the comparison report compiles + synthetic ablation table renders): "what would an examiner attack first about this ablation methodology?" → `.sisyphus/codex/sha-32-ablation-2026-05-01.md` — invoked? **no, planned**

## Status
- 2026-05-01: Worktree created from `main@1b6248b`. 194 eval tests pass on baseline. Survey done. Phase 5 plan written. Starting Task 1 (adapter).
