# WORKTREE — SHA-TBD: LLM-assisted gold-set labeling pipeline

**Linear**: pending creation; child of SHA-14 / successor to the deferred-paralegal track in SHA-28.
**Branch**: `feature/sha-28-llm-labeling-pipeline`
**Created**: 2026-05-02 off `main@29a0cf6`.

## What this worktree owns

Implementation of the dual-LLM + auto-grounder + human-adjudication labeling pipeline described in `.sisyphus/codex/sha-tbd-llm-labeling-2026-05-02.md` (Codex-revised). Replaces the two-paralegal Phase 3 + Phase 6 of `.sisyphus/plans/track-a-plan.md`.

## Files allowed

- `packages/eval/auto_label/**` (new package)
- `packages/eval/schema.py` (extend with `LabelingProvenance`)
- `packages/eval/tests/**` (new tests for new modules)
- `packages/llm_orchestrator/clients/labeler_factory.py` (new)
- `packages/llm_orchestrator/tests/**` (new labeler-factory tests)
- `scripts/eval/auto_label.py` (new)
- `scripts/eval/adjudicate.py` (new)
- `data/eval/labeling_examples/positive/**` (positive few-shot exemplars)
- `docs/eval/gold-schema.md` (provenance section)
- `docs/eval/reviewer-guide.md`, `docs/eval/reviewer-log.md` (adjudicator-only reframe)
- `docs/superpowers/plans/2026-05-02-llm-labeling-pipeline.md` (TDD plan)
- `.sisyphus/plans/track-a-plan.md` (Phase 3 + Phase 6 rewrite)
- `.sisyphus/notepads/llm-labeling/**` (decision-log entries, scratch)

## Files forbidden

- `apps/**` — owned by other tracks
- `packages/eval/case_file_adapter.py` (read-only — leakage contract)
- `packages/eval/leakage.py` (read-only — leakage contract)
- `data/eval/negative_sets/**` (hand-crafted; do not touch)
- `data/gold_standard/housing_v1.jsonl` (do not append until full pipeline + gates land)

## DoD (carried from sparring plan §What lands when)

- [ ] `LabelingProvenance` + `GoldCase.labeling_provenance` shipped with tests
- [ ] Canonicalizer, span matcher, and bounded OCR-drift recovery shipped with tests
- [ ] `LabelerModelSpec` + dual-provider factory helper shipped, tests prove A/B independence
- [ ] Field-path-level `DisagreementSet` shipped with tests
- [ ] Real-gold append gate refuses every condition listed in §8 of the sparring plan
- [ ] Facts leakage scanner rejects verdict/award/finding language
- [ ] Auto-grounder runs every per-field check listed in §3 of the sparring plan
- [ ] Labeler runner writes per-case artifact under `data/eval_artifacts/labeling/<run_id>/<case_id>.json`
- [ ] `scripts/eval/auto_label.py` and `scripts/eval/adjudicate.py` end-to-end on a fixture
- [ ] `track-a-plan.md` Phase 3 + Phase 6 rewritten; decision-log entry committed
- [ ] All `packages/eval/tests/` green; coverage gate held; no Edit to `case_file_adapter.py` or `leakage.py`

## Status

- 2026-05-02: worktree created off `main@29a0cf6`. Baseline `pytest packages/eval` green (368/368). Plan to land at `docs/superpowers/plans/2026-05-02-llm-labeling-pipeline.md`. Subagent-driven execution.
