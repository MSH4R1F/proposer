# One-case housing.repairs_social.v1 KG positive-control fixture

Stream C recovery sprint, Task 7 (data portion).

## What this is

A **hand-crafted, self-consistent KG fixture** for a single synthetic
`housing.repairs_social.v1` case, populated to the level the
`FactorRetriever` and `EvidencePathValidator` actually need to fire
(rather than fall back to chunk-RAG, as in the 2026-05-07 ablation).

The fixture is the substrate for the positive-control smoke tests that
land in a follow-up commit. When it is wired through
`PredictionEngineV2` with `STREAM_C_FACTOR_RETRIEVAL=1`, the engine
should produce metadata showing:

- `kg_used_for_prediction = True`
- `retrieval_strategy = factor_constrained`
- `evidence_path_supported = True`
- `comparator_pack_size > 0`
- `counterexample_pack_size > 0`

## Why a positive control

The 2026-05-07 forced-answer ablation showed `hybrid` and `rag_only`
within CI overlap, with `kg_used_for_prediction=False` on every
`hybrid` row — suggesting the FactorRetriever was systematically
falling back. The positive control isolates the question:
"if the data were genuinely there, would the KG path light up?"
A green smoke test on this fixture is a precondition for any further
data backfill work (recovery plan §Gate 3).

## Fact pattern

A synthetic damp/mould case:

- Resident is a single parent with diagnosed asthma; one young child
- Damp and mould reported on 12 December 2024; landlord acknowledged
  the same day
- First inspection: 11 April 2025 (120 days after report)
- Substantive repairs completed: 10 June 2025 (180 days after notice)
- Two correspondence gaps of >6 weeks during the period
- No alternative accommodation, no apology or compensation pre-determination
- Determination: `maladministration`

The fact pattern is deliberately tilted toward a clear `fault_finding`
outcome so the smoke test has unambiguous expectations.

## Files

| File | Purpose |
| --- | --- |
| `case.json` | Single `eval.schema.GoldCase` row (synthetic, deterministic SHA256) |
| `evidence_spans.json` | 5 `EvidenceSpan` instances backing the factor assertions |
| `factor_assertions.json` | 7 `FactorAssertion` instances (4 boolean + 2 duration + 1 enum), all `extraction_method=manual_gold` |
| `propositions.json` | 8 `Proposition` instances: 6 fault_finding comparators + 2 no_fault counterexamples |
| `outcome_components.json` | 1 `OutcomeComponent` for `fault_finding`, linked back to factors and propositions |
| `expected_outcome.json` | Gold label + expected engine metadata for the smoke test |
| `validate_fixture.py` | Standalone Pydantic round-trip + cross-reference validator |
| `README.md` | This file |

## Determinism

All UUIDs in `propositions.json` are `uuid5` derived from stable strings
(see the generator snippet in `validate_fixture.py`'s commit).
`source_pdf_sha256` is the SHA256 of a fixed string. No timestamps appear
inside any value, so the smoke test in the follow-up commit is
reproducible across machines.

## Validation

```bash
PYTHONPATH=packages ./venv/bin/python \
    data/eval_artifacts/positive_control/housing_repairs_social_v1_one_case_kg/validate_fixture.py
```

Exits 0 on success. Checks performed:

1. Each entry round-trips through its Pydantic model
   (`GoldCase`, `EvidenceSpan`, `FactorAssertion`, `Proposition`,
   `OutcomeComponent`)
2. Every `factor_assertion.factor_id` is in
   `packages/domain_packs/housing/repairs_social/factors.yaml`
3. Every `factor_assertion.supported_by` ID resolves to an
   `EvidenceSpan`
4. Every `outcome_component.supporting_factor_ids` ID resolves to a
   `FactorAssertion.factor_id`
5. Every `outcome_component.supported_by_propositions` UUID resolves
   to a `Proposition`
6. Every `proposition.factor_ids` entry is in the catalog
7. `expected_outcome.determination` is in `outcomes.yaml`

## Naming conventions chosen for this fixture

- `claim_head_id = "repairs_damp_mould"` — matches the convention
  in `packages/legal_core/tests/test_outcome_component.py` and the
  module-level docstring on `outcome_component.py`. There is currently
  no enumerated catalog of claim_head_ids in the domain pack, so this
  name is informal but consistent with existing tests.
- `outcome_component_ids` on `Proposition` are set to either
  `"fault_finding"` or `"no_fault"`. These pseudo-outcomes match the
  string the FactorRetriever passes as `primary_outcome` (see
  `packages/llm_orchestrator/pipeline/issue_retrieval.py:359-365`),
  not the formal `Determination` enum used by `GoldCase`.
- `outcome_component.outcome_id = "fault_finding"`. The
  `OutcomeComponent.outcome_id` field references
  `OutcomeSchema.outcomes[].id` from the domain pack; the comment in
  the model file explicitly cites `fault_finding` as the example.

## Known caveats

- The fixture intentionally has `claimed_amounts = []` and
  `total_awarded_gbp = 0`. The smoke test only checks KG-path
  activation, not award reconstruction.
- `statutory_basis` is empty with an explicit unavailability reason.
  Real cases would carry statute citations; for a synthetic fixture
  any citations would be fabricated.
- `case_size = "unknown"` because `disputed_amount_gbp` is null
  (INV-7 enforces this pairing).
