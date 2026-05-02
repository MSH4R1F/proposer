# Frozen Deposit Golden-Output Parity Fixtures

**Status:** STUB (Phase 1 Task 1.6, SHA-20).

## Why this is a stub

The plan's Task 1.6 requires deterministic regression fixtures that prove
adding domain plumbing does not change deposit-flow outputs. To produce a
realistic `expected_prediction.json` we need to capture a snapshot from the
existing orchestrator engine.

Worker A (Phase 1, this commit) cannot do that without importing
`llm_orchestrator`/`rag_engine`, which would violate the leaf-dependency
invariant enforced by `packages/domain_core/tests/test_import_boundary.py`.

Therefore:

- `input_case_file.json`, `knowledge_graph.json`, and `rag_results.json` are
  realistic-shape stubs sufficient for downstream subagents to wire the
  parity harness without re-fabricating the inputs.
- `expected_prediction.json` is a stub with `"status": "stub"`. The test
  `packages/domain_core/tests/test_domain_fixtures.py::test_frozen_deposit_parity_skipped_until_engine_snapshot`
  detects the stub status and `pytest.skip`s with an explicit reason.

## How to un-stub

A later phase (likely Phase 3 once `domain_id` is threaded as a no-op) must:

1. Run the existing deposit pipeline against `input_case_file.json` with a
   stubbed LLM and the fixed `rag_results.json`.
2. Snapshot the orchestrator output to `expected_prediction.json`,
   normalizing timestamps, trace IDs, UUIDs, latency, and cost fields.
3. Replace the stub `expected_prediction.json` and re-enable the parity
   assertion (delete the `"status": "stub"` short-circuit in the test).
4. Re-run `pytest packages/domain_core/tests` and confirm the parity test
   actively asserts (no skip).

## Acceptance criteria for un-stubbing (from plan)

The parity test must assert structural parity on:

- winner / outcome classification
- monetary amount and remedy breakdown
- issue outcomes
- citation case refs / source IDs / source URLs / cited spans
- IRAC / reasoning section labels
- legal-information disclaimer text

with these fields normalized: timestamps, trace IDs, UUIDs, provider
latency, cost.
