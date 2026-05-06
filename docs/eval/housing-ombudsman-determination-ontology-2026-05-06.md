# Housing Ombudsman Determination Ontology — Canonical Mapping (2026-05-06)

Companion to [`packages/eval/schema.py::Determination`](../../packages/eval/schema.py) and the migration script [`scripts/eval/migrate_balanced50_to_determination_schema.py`](../../scripts/eval/migrate_balanced50_to_determination_schema.py) (Task 15 of the determination-ontology plan).

This document is the single source of truth for:
- the seven Housing Ombudsman determination classes (`Determination`),
- the canonical `Determination → Winner` mapping (`overall_winner_legacy`),
- the canonical `outcome_normalized → Determination` mapping used by the auto-labeler manifest,
- the canonical default amount-split rule (which of the three split fields receives `total_awarded_gbp` for each determination class),
- the human-escalation queue: cases the default split cannot reliably resolve.

The mapping is implemented authoritatively in code at `packages/eval/schema.py::_legacy_winner_for` and `scripts/eval/migrate_balanced50_to_determination_schema.py::map_outcome_normalized_to_determination` / `split_amount_by_determination`.

---

## 1. Determination → legacy Winner mapping

| `determination`              | `overall_winner_legacy` |
|------------------------------|-------------------------|
| `maladministration`          | `tenant`                |
| `severe_maladministration`   | `tenant`                |
| `service_failure`            | `tenant`                |
| `reasonable_redress`         | `landlord`              |
| `no_maladministration`       | `landlord`              |
| `outside_jurisdiction`       | `landlord`              |
| `resolved_with_intervention` | `split`                 |

Authoritative source: [`packages/eval/schema.py::_legacy_winner_for`](../../packages/eval/schema.py).

Notes:
- `outside_jurisdiction` is mapped to `landlord` by convention because the Ombudsman did not order any new pay-out from the landlord. This is **not** a substantive merits win — eval metrics should test for **abstention** on these rows rather than scoring an outcome (see [`docs/eval/metrics.md`](metrics.md)).
- `resolved_with_intervention` is a settlement during the Ombudsman investigation; mapping to `split` reflects the lack of a clean tenant-or-landlord merits decision.

---

## 2. `outcome_normalized` (manifest tag) → `Determination` mapping

The auto-labeler manifest carries an `outcome_normalized` tag for each case. The migration script maps each manifest tag to its canonical `Determination` value:

| `outcome_normalized` (manifest) | `determination` (schema) |
|---------------------------------|---------------------------|
| `maladministration`             | `maladministration`       |
| `severe-maladministration`      | `severe_maladministration`|
| `service-failure`               | `service_failure`         |
| `reasonable-redress`            | `reasonable_redress`      |
| `no-maladministration`          | `no_maladministration`    |
| `outside-jurisdiction`          | `outside_jurisdiction`    |
| `resolved-with-intervention`    | `resolved_with_intervention` |

Mismatch policy: a manifest tag absent from this table raises `KeyError` in `map_outcome_normalized_to_determination`. The case is then flagged in `migration_review_queue.jsonl` for human escalation rather than silently coerced.

---

## 3. `total_awarded_gbp` → split fields default rule

Default deterministic split when no per-complaint breakdown is available (the migration script's `split_amount_by_determination`):

| `determination`                   | `amount_ordered_now_gbp` | `amount_previously_offered_gbp` | `amount_global_unapportioned_gbp` |
|-----------------------------------|--------------------------|---------------------------------|-----------------------------------|
| `maladministration` / `severe_mal` / `service_failure` | `total`                  | `None`                          | `None`                            |
| `reasonable_redress`              | `None`                   | `total`                         | `None`                            |
| `resolved_with_intervention`      | `None`                   | `None`                          | `total`                           |
| `outside_jurisdiction`            | `None` (total must be 0) | `None`                          | `None`                            |
| `no_maladministration`            | `None` (total usually 0) | `None`                          | `None`                            |

Sum invariant: when any of the three split fields is set, their sum equals `total_awarded_gbp` exactly (`packages/eval/schema.py::GroundTruthOutcome._validate_outcome` / INV-D1). Setting all three to `None` (the default) is permitted and skips the split.

Zero-total invariant: `outside_jurisdiction` rows must have `total_awarded_gbp == 0` and all three split fields `None` (INV-D2).

---

## 4. Cases requiring human escalation

The default split (§3) is approximate. Cases the migration script flags into `migration_review_queue.jsonl` for batched human review:

1. **Maladministration / service-failure cases with both a fresh order AND a previously-offered amount.** Examples on the balanced-50: `housing-ombudsman-202402680` (£100 ordered + £1,250 previously offered), `housing-ombudsman-202341372` (£100 ordered + £300 previously offered). The default rule allocates 100% to `amount_ordered_now_gbp`, which under-counts. Reviewer must split manually.
2. **Mixed determinations** (`outcome_raw` contains `;`). On the balanced-50, 24/50 cases match. Each complaint head deserves its own `ComplaintFinding` entry under `determination_per_complaint`.
3. **Internal source inconsistencies.** Examples: `housing-ombudsman-202326338` references both £925 and £150 in the recommendation; `housing-ombudsman-202408843` references £750 and £850. The migration script writes whichever value the gold v1 already chose; reviewer should re-extract from the source PDF.
4. **`outcome_normalized` tag absent from §2.** Migration raises and the case is flagged.
5. **`outside_jurisdiction` rows with non-zero `total_awarded_gbp` in v1 gold.** The migration script raises `ValueError`; reviewer must reconcile.

The migration writes one JSONL row per flagged case to `data/eval_artifacts/migration/balanced_50_2026_05_06/migration_review_queue.jsonl` of the form `{"case_id": "...", "flags": ["mixed_outcome_raw:...", "packet_not_found", ...]}`.

---

## 5. Cite-or-abstain implication

`outside_jurisdiction` cases are non-determinations. The orchestrator's housing prompt pack (`packages/llm_orchestrator/prompts/packs/housing_repairs_social_v1.py::_OMBUDSMAN_PREDICTION_SYSTEM`) instructs the model to abstain (`outcome='uncertain'`) on this class. Eval metrics (`packages/eval/metrics/accuracy.py::determination_accuracy`) scope the denominator to cases that carry a gold `determination`; combined with the schema's INV-D4 (housing.repairs_social.v1 rows must set `determination`), out-of-jurisdiction cases are still scored — but a correctly-abstaining model registers as `predicted_determination=outside_jurisdiction` (or `None`, which counts as wrong unless the row's gold determination matches).

For "is the model honest about non-determinations?" reporting, prefer the per-class recall on `OUTSIDE_JURISDICTION` (`determination_class_recall(...)[Determination.OUTSIDE_JURISDICTION]`) rather than headline accuracy.

---

## 6. Versioning & change-control

Changes to this mapping require a coordinated edit across:

1. `packages/eval/schema.py` — `Determination` enum, `_legacy_winner_for`, INV-D2/D3/D4 validators.
2. `packages/llm_orchestrator/models/prediction_v2.py` — orchestrator-side `Determination` enum (kept in lock-step by string value).
3. `packages/eval/auto_label/prompts/extraction.py` — labeler guidance (bump `PROMPT_PACK_VERSION`).
4. `packages/llm_orchestrator/prompts/packs/housing_repairs_social_v1.py` — production prompt block.
5. `scripts/eval/migrate_balanced50_to_determination_schema.py` — migration helpers.
6. `data/gold_standard/housing_repairs_social_v2.jsonl` — re-run migration.
7. This document.

Tests guarding the mapping:
- `packages/eval/tests/test_schema_determination.py::TestDeterminationEnum::test_legacy_winner_for_handles_every_determination`
- `packages/eval/tests/test_schema_determination.py::TestGroundTruthOutcomeExtended` (sum / outside-jurisdiction / legacy-winner invariants)
- `packages/llm_orchestrator/tests/test_prediction_v2_determination.py` (orchestrator enum mirror)
- `packages/eval/tests/test_auto_label_extraction_prompt.py` (labeler prompt presence)
- `packages/llm_orchestrator/tests/test_housing_prompt_determination.py` (prediction prompt presence)

If you add a new `Determination` value (e.g. `partial_maladministration`), every item above must be updated in a single PR; the exhaustiveness test in `test_legacy_winner_for_handles_every_determination` will catch missing cases in `_legacy_winner_for`.

---

## 7. End-to-end wiring (post-mortem)

PR #32 added the schema/adapter/metrics/orchestrator-side fields. The first end-to-end smoke run (Task 17 of the implementation plan) revealed the wiring was incomplete in three additional places that PR #32 didn't touch — the LLM still emitted the new fields, but they were dropped before the metrics could see them. PR #33 closed all three:

1. **Production user prompt** (`packages/llm_orchestrator/pipeline/issue_predictor.py::_format_repairs_user_prompt`). The IRAC system prompt told the model about the new fields, but the user prompt's "before choosing the final JSON" paragraph only enumerated `outcome` / `predicted_amount` / `amount_band` and treated the new fields as optional. The model dropped them. Fixed by adding an explicit "REQUIRED housing.repairs_social.v1 fields — do not omit" paragraph at the bottom of the user prompt.

2. **JSONL serializer** (`scripts/eval/predict_all.py::_serialise_prediction`). The eval-side `Prediction` dataclass had the fields populated by `_adapt_determination`, but `_serialise_prediction` built the JSONL output from a hand-coded field list that omitted them. Fixed by adding `predicted_determination` to the top-level dict and `amount_construct` to the per-issue dict.

3. **JSONL loader** (`packages/eval/run.py::_dict_to_prediction`). Symmetrical to (2) — even after the JSONL had the fields, the loader built `Prediction` objects without reading them, so all metric calls saw `None`. Fixed by parsing `predicted_determination` back to the eval-side `Determination` enum and threading `amount_construct` through to `IssuePrediction`.

When extending the ontology in the future (e.g. adding a `partial_maladministration` value, or a fourth `amount_construct`), the change-control checklist in §6 covers the schema/orchestrator/prompt/labeler surfaces. **Also verify these three serialisation seams** — they are not symbol-name searchable from the schema and are easy to forget. The exhaustiveness tests in `test_legacy_winner_for_handles_every_determination` and the housing prompt snapshot tests cover the schema/prompt sides; `test_run_summary_determination.py` and `test_adapter_determination.py` cover the metrics/adapter sides; the serializer/loader sides are covered indirectly via the smoke run in [`docs/eval/housing-ombudsman-stratified-50-v2-eval-2026-05-06.md`](housing-ombudsman-stratified-50-v2-eval-2026-05-06.md).

Lesson for future per-domain field additions: any field that needs to flow LLM → eval metrics has six seams that all need the field name in them — Pydantic model, parser, assembler, adapter, serializer, loader. The eval/orchestrator package boundary makes a single grep insufficient; the smoke run is the test that exercises all six together.
