# Gold-Case Schema (`housing_v1`)

> **Status:** `v1` is **mutable** until both conditions are met:
>
> 1. The full Phase 3 pilot batch (10 reviewer-signed-off cases) is committed to `data/gold_standard/housing_v1.jsonl`, AND
> 2. Every HIGH-severity Codex sparring action item in `.sisyphus/codex/sha-28-schema-2026-04-27.md` is resolved (accepted-and-implemented, or rejected with recorded rationale).
>
> Until both conditions hold, `v1` may be edited in place — including breaking field changes — without bumping the version. Once frozen, any field change requires a `v2` bump and a fresh JSONL file alongside the old one. See [SHA-95](https://linear.app/sharifbuilders/issue/SHA-95).

This document describes the Pydantic schema in `packages/eval/schema.py` that backs every gold-standard case used by the evaluation harness. Each annotated case is a single JSON object conforming to `GoldCase`; the corpus is stored as JSONL (one case per line) at `data/gold_standard/housing_v1.jsonl`.

The schema is the load-bearing contract for every downstream metric — accuracy, Brier/ECE, citation precision, RAGAS, hallucination audit, ablation runner. Mistakes here propagate into every thesis number.

## Linear

- Epic: [SHA-14](https://linear.app/sharifbuilders/issue/SHA-14) — Evaluation Infrastructure & Gold Standard
- Critical-path child: [SHA-28](https://linear.app/sharifbuilders/issue/SHA-28) — Build gold standard test set

## File layout

| Path | Contents |
|---|---|
| `data/gold_standard/housing_v1.jsonl` | Production corpus. One `GoldCase` JSON per line. |
| `packages/eval/schema.py` | The Pydantic models — single source of truth. |
| `packages/eval/tests/fixtures/gold_case_minimal.json` | Synthetic round-trip fixture used by the test suite and by this document as the canonical example. |
| `docs/eval/reviewer-log.md` | Paralegal reviewer sign-off log (one entry per case; populated during Phase 6). |

## Top-level model: `GoldCase`

| Field | Type | Notes |
|---|---|---|
| `schema_version` | enum `SchemaVersion` | Always `"v1"` at present. Bumped on any breaking field change. |
| `case_id` | string, non-empty | Stable identifier across regenerations (e.g. `"FTT-PR-2023-0042"`). |
| `decision_date` | ISO date | Must fall in `2019-01-01 .. 2024-12-31` (PILOT window). |
| `region` | enum `RegionUK` | Normalised UK region, e.g. `"london"`, `"north_west"`, `"wales"`. Used for the 30/70 stratification audit. |
| `region_source` | string | Verbatim region text from the source PDF, kept for reviewer provenance. |
| `case_size` | enum `CaseSize` | `"small"` if `disputed_amount_gbp` ≤ £1500, `"large"` if above £1500, or `"unknown"` when a domain does not expose a clean pre-decision monetary dispute value. Cross-validated against `disputed_amount_gbp` (INV-7), not against summed `claimed_amounts` (which can double-count mirrored claim/counterclaim entries). |
| `disputed_amount_gbp` | `Decimal`, ≥0, or `null` for supported unknown-amount domains | Canonical pre-decision dispute value, independent of any one party's claim. Drives stratification when present — see [SHA-91](https://linear.app/sharifbuilders/issue/SHA-91) for why this is independent of `claimed_amounts`. For `housing.repairs_social.v1`, keep this `null` unless the source exposes a clean pre-decision claimed/disputed amount; do not copy a final Ombudsman compensation order into this field. |
| `claim_types` | list of enum `ClaimType`, ≥1 | One or more of `cleaning`, `damages`, `deposit_non_protection`, `disrepair`, `end_of_tenancy`. Multi-type cases are common (a single decision can hit cleaning + damages + disrepair). Stratification target ("≥5 cases per claim type") is computed as: for each type `t`, `t in case.claim_types` for ≥5 cases. See [SHA-92](https://linear.app/sharifbuilders/issue/SHA-92). |
| `source_pdf_sha256` | string | 64-char lowercase hex — SHA-256 of the source tribunal PDF. Lets reviewers re-fetch and re-OCR independently. |
| `ocr_confidence` | float ∈ [0,1] or `null` | OCR confidence of the source extraction; `null` when source is text-native. |
| `parties` | list of `Party` | At least one `tenant` and one `landlord`. `agent` permitted as third role. |
| `facts` | string, ≥50 chars | Plain-English summary of the dispute. |
| `evidence` | list of `Evidence` | Discrete pieces of evidence relied on by the tribunal. |
| `statutory_basis` | list of `StatutoryReference` | Statutes cited by the decision. |
| `cited_authorities` | list of `Authority`, default `[]` | Case-law authorities cited by the tribunal. Empty list permitted (some decisions cite none). Phase 2 `dataset.audit()` uses this for the temporal-leakage check: a training case must not cite an authority decided after the train-window cutoff. See [SHA-90](https://linear.app/sharifbuilders/issue/SHA-90). |
| `claimed_amounts` | list of `ClaimedAmount`; may be empty for supported unknown-claim domains | Each is `(issue, amount_gbp, by_party)`. The `issue` field is a free-text label that **must match** the `issue` on every `IssueOutcome` in `ground_truth_outcome.per_issue` (INV-5). For `housing.repairs_social.v1`, leave this empty unless there is clean pre-decision claim provenance; final Ombudsman awards belong only in `ground_truth_outcome`. |
| `ground_truth_outcome` | `GroundTruthOutcome` | The judge's actual decision. |
| `key_reasoning_quotes` | list of `ReasoningQuote`, ≥1 | Quotes lifted from the decision text. Every quote must carry structured `provenance` so reviewers can locate it in the source PDF. |

## Sub-models

### `Party`

| Field | Type | Notes |
|---|---|---|
| `role` | enum `PartyRole` | `tenant`, `landlord`, or `agent`. |
| `represented` | bool | Did the party appear with a lawyer or formal representative? |

### `Evidence`

| Field | Type | Notes |
|---|---|---|
| `kind` | string | Free text: e.g. `photo`, `invoice`, `tenancy_agreement`, `inspection_report`, `bank_statement`. |
| `description` | string | Plain-English description. |
| `provenance` | `Provenance` or `null` | Structured `{page, paragraph, optional text_span}` location in the decision PDF. |

### `StatutoryReference`

| Field | Type |
|---|---|
| `statute` | e.g. `"Housing Act 2004"` |
| `section` | e.g. `"s.213"` |
| `provenance` | `Provenance` or `null` |

### `Authority`

| Field | Type | Notes |
|---|---|---|
| `name` | string, non-empty | e.g. `"Howard de Walden Estates Ltd v Aggio"`. |
| `court` | string or `null` | e.g. `"UKSC"`, `"EWCA Civ"`, `"FTT(PC)"`. |
| `cited_date` | ISO date | Decision date of the **cited** authority (not of the current case). Used by the temporal-leakage audit. |
| `provenance` | `Provenance` or `null` | Where in the *current* decision this authority is cited. |

### `ClaimedAmount`

| Field | Type |
|---|---|
| `issue` | string label, must appear in `ground_truth_outcome.per_issue` |
| `amount_gbp` | `Decimal`, ≥0 |
| `by_party` | which party is claiming this |

### `IssueOutcome` (member of `GroundTruthOutcome.per_issue`)

| Field | Type |
|---|---|
| `issue` | string label, must match a `claimed_amounts.issue` |
| `winner` | `tenant` / `landlord` / `split` |
| `awarded_gbp` | `Decimal`, ≥0 |

### `GroundTruthOutcome`

Two paths are permitted:

* **Apportioned** (default, `unapportioned_reason is None`): tribunal broke the award down per issue. INV-6 enforces `total_awarded_gbp == sum(per_issue.awarded_gbp)` exactly.
* **Unapportioned** (`unapportioned_reason` is a non-empty string): tribunal gave a global figure with no per-issue breakdown. `per_issue` MUST be empty; INV-5 (per-issue/claimed-amounts label match) is vacuously satisfied; the annotator must record *why* the decision is unapportioned. See [SHA-91](https://linear.app/sharifbuilders/issue/SHA-91).

| Field | Type | Notes |
|---|---|---|
| `overall_winner` | `tenant` / `landlord` / `split` | The headline outcome. |
| `total_awarded_gbp` | `Decimal`, ≥0 | Apportioned: must equal `sum(per_issue[].awarded_gbp)` exactly (INV-6). Unapportioned: authoritative figure as given by the tribunal. |
| `per_issue` | list of `IssueOutcome`, default `[]` | Apportioned: ≥1. Unapportioned: must be `[]`. |
| `unapportioned_reason` | string or `null` | Set iff the case is unapportioned. Records *why* the tribunal declined to break the award down. |

### `Provenance`

| Field | Type | Notes |
|---|---|---|
| `page` | int, ≥1 | 1-indexed source PDF page. |
| `paragraph` | int, ≥1 | 1-indexed paragraph or reviewer paragraph marker. |
| `text_span` | `[start, end]` or `null` | Optional character span in normalised page text; must satisfy `0 <= start < end`. |

### `ReasoningQuote`

| Field | Type | Notes |
|---|---|---|
| `text` | string, ≥1 char | Verbatim quote from decision. |
| `provenance` | `Provenance` | **Required** — every quote must be locatable in source PDF. |

## Cross-field invariants

These are enforced by `@model_validator(mode="after")` on `GoldCase` (and `GroundTruthOutcome` for INV-6). Field-level constraints (`Field(ge=0)`, `min_length=...`) are enforced inline.

| ID | Rule | Where enforced | Why |
|---|---|---|---|
| INV-1 | `decision_date` in `[2019-01-01, 2024-12-31]` | `GoldCase` | PILOT temporal-split window. Case outside window is either training-set leakage or out-of-distribution. |
| INV-2 | `parties` includes ≥1 `tenant` and ≥1 `landlord` | `GoldCase` | A deposit-dispute case without both parties is an annotation error. |
| INV-3 | `ocr_confidence` ∈ `[0,1]` when set; `null` allowed | `Field(ge=0, le=1)` on `GoldCase` | Sanity check on OCR pipeline output; `null` lets text-native PDFs bypass. |
| INV-4 | `source_pdf_sha256` matches `^[0-9a-f]{64}$` | `GoldCase` | Stops typos and accidental UPPERCASE; reviewer can recompute and confirm. |
| INV-5 | Every `ground_truth_outcome.per_issue[].issue` appears in `claimed_amounts[].issue` (apportioned path only; vacuously satisfied when unapportioned) | `GoldCase` | The judge cannot decide an issue that no party claimed; mismatch is an annotation drift between the two lists. |
| INV-6 | `ground_truth_outcome.total_awarded_gbp == sum(per_issue[].awarded_gbp)` exactly, when `unapportioned_reason is None`. When `unapportioned_reason` is set, `per_issue` must be empty and INV-6 is bypassed. | `GroundTruthOutcome` | Catches arithmetic typos at annotation time on the apportioned path; lets unapportioned global awards into the corpus. |
| INV-7 | `case_size == small` iff `disputed_amount_gbp <= £1500` | `GoldCase` | The 30/70 stratification audit is run from the corpus alone. Defined against the canonical dispute value rather than `sum(claimed_amounts)`, which can double-count mirrored claims. |
| INV-8 | `Decimal` amounts never negative | `Field(ge=0)` on `ClaimedAmount`, `IssueOutcome`, `GroundTruthOutcome`, `GoldCase.disputed_amount_gbp` | Tribunal awards cannot be negative; negative values are sign errors. |
| INV-9 | `overall_winner` agrees with the `per_issue.winner` aggregate (apportioned path only). Aggregation rule: if every per-issue winner is the same value V, then `overall_winner == V`; otherwise `overall_winner == split`. Skipped when `unapportioned_reason` is set. | `GoldCase` | Without this, a `winner=tenant` case can validate while every per-issue outcome favours landlord, silently corrupting the headline accuracy label. See [SHA-93](https://linear.app/sharifbuilders/issue/SHA-93). |
| INV-10 | `evidence` and `statutory_basis` must each be non-empty, or carry a non-empty `*_unavailable_reason`. A reason cannot be set when the corresponding list is non-empty. | `GoldCase` | Prevents silent omission of source support while still allowing decisions with no published evidence/statutory basis. |

## Canonical example

```json
{
  "schema_version": "v1",
  "case_id": "SYNTH-2023-0001",
  "decision_date": "2023-06-15",
  "region": "london",
  "region_source": "London",
  "case_size": "small",
  "disputed_amount_gbp": "400.00",
  "claim_types": ["cleaning"],
  "source_pdf_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "ocr_confidence": 0.92,
  "parties": [
    {"role": "tenant", "represented": false},
    {"role": "landlord", "represented": true}
  ],
  "facts": "Tenant occupied flat from 2022-01-01 to 2023-05-31; landlord retained 400 GBP of the 1200 GBP deposit citing carpet cleaning and disputed the deduction.",
  "evidence": [
    {"kind": "invoice", "description": "Carpet cleaning invoice for 180 GBP", "provenance": {"page": 1, "paragraph": 7}}
  ],
  "statutory_basis": [
    {"statute": "Housing Act 2004", "section": "s.213", "provenance": {"page": 1, "paragraph": 12}}
  ],
  "claimed_amounts": [
    {"issue": "carpet_cleaning", "amount_gbp": "400.00", "by_party": "landlord"}
  ],
  "ground_truth_outcome": {
    "overall_winner": "tenant",
    "total_awarded_gbp": "220.00",
    "per_issue": [
      {"issue": "carpet_cleaning", "winner": "tenant", "awarded_gbp": "220.00"}
    ]
  },
  "key_reasoning_quotes": [
    {"text": "The landlord adduced no evidence beyond a single invoice.", "provenance": {"page": 2, "paragraph": 14}}
  ]
}
```

This is the same JSON committed at `packages/eval/tests/fixtures/gold_case_minimal.json` — kept in sync via the `TestGoldCaseRoundTrip` tests.

## Versioning policy

- `v1` is **mutable until** (a) the full Phase 3 pilot batch (10 cases) is reviewer-signed-off and (b) every HIGH-severity item in `.sisyphus/codex/sha-28-schema-2026-04-27.md` is resolved. Either condition unmet → `v1` may be edited in place without a version bump. See [SHA-95](https://linear.app/sharifbuilders/issue/SHA-95).
- Once both conditions are met, `v1` is **frozen**. Any field addition, removal, type change, or invariant change after that point requires:
  1. Bump `SchemaVersion` to `v2`, leaving `v1` enum value present for backward-compatible reads.
  2. Create `data/gold_standard/housing_v2.jsonl` (new file; do not mutate `housing_v1.jsonl`).
  3. Provide a migration script under `scripts/eval/migrate_v1_to_v2.py` if the change is mechanical.
  4. Update this document and the Codex sparring record.
- Adding an **enum value** (e.g. a new `ClaimType`) is technically a breaking change for downstream stratification logic — bump `v1.x` → `v2`.

## Known limitations / future work

- `evidence.kind` is free text — same closed-enum question as `region` had before SHA-98.
<!-- (former `claim_type` single-valued limitation resolved in SHA-92) -->
- Per-party representation captured as a single bool; reviewer noted that "self-represented but with paid McKenzie friend" is a real category. Defer until corpus shows ≥5 such cases.

These limitations are surfaced in the Codex sparring template at `.sisyphus/codex/sha-28-schema-2026-04-27.md`.

## Labeling provenance (sparring plan §6)

When a `GoldCase` row is produced by the LLM-assisted labeling pipeline (`packages/eval/auto_label/runner.py`), it carries a `labeling_provenance: LabelingProvenance` field that captures the full audit trail needed to replay the decision once labeler models, OCR engines, or authority indexes drift. Rows that pre-date the pipeline (legacy hand-annotated cases) leave `labeling_provenance = None`.

The schema is split across three Pydantic classes in `packages/eval/schema.py`:

### `LabelerModel`

A single labeling pass's `provider` (`"anthropic"` or `"openai"`), `model` string, and optional `api_version`. Recorded per case so a published gold set can be re-derived from the raw LLM outputs (frozen in the run artifact, see below) even after the live model is retired.

### `FieldLabelProvenance`

Per-cell audit trail for a single `GoldCase` field. Fields:

- `field_path` — a granular identifier for the cell, using the notation defined in §4 of the sparring plan (e.g. `"per_issue[issue=damages].winner"`, `"key_reasoning_quotes[0].text"`). The canonical builder will live in `packages/eval/auto_label/disagreement.py`.
- `source` — one of the closed `_PROVENANCE_SOURCES` literal values:
  - `deterministic_manifest` — value came from the corpus manifest, not from any LLM.
  - `model_agreement` — both labeler models agreed and the auto-grounder accepted the cell.
  - `human_mandatory_review` — adjudicator reviewed and confirmed the cell because the field is in the MandatoryReviewSet (§1 of the sparring plan), regardless of model agreement.
  - `human_disagreement_adjudication` — adjudicator broke a model-vs-model tie.
  - `human_agreed_cell_audit` — cell was sampled into the 10% audit overlay and confirmed (or flipped — see `LabelingProvenance.audit_flip_rate`).
  - `human_only_anchor` — case is part of the 10–20-case human-only anchor set; no LLM was consulted.
- `source_spans` — list of `Provenance` triples grounding the cell to the source PDF.
- `match_strategy` — when set, names the span-matcher strategy that grounded the cell (`"canonical_exact"`, `"bounded_fuzzy"`, ...).
- `reviewer_rationale` — optional free-text note from the human adjudicator.

### `LabelingProvenance`

Per-case audit trail. Carries every hash and version needed to replay a labeling decision. Notable fields:

- `run_id`, `labeled_at` — when this case was labeled and under which run.
- `labeler_models` — at least one `LabelerModel`. Two-pass dual-LLM runs record both.
- Reproducibility hashes / versions: `source_pdf_sha256`, `ocr_text_sha256`, `prompt_template_hash`, `gold_schema_hash`, `corpus_manifest_hash`, `canonicalizer_version`, `grounder_version`, plus optional fields for OCR engine, prompt pack, domain spec, and authority/statute index identifiers.
- `audit_seed` — the deterministic random seed for the 10% audit sample.
- Human-control flags: `is_human_only_anchor`, `anchor_set_id`, `mandatory_review_completed_at`, `human_adjudicator`, `adjudicated_fields`.
- Reported metrics — all in the `[0, 1]` interval, all **raw rates** rather than Cohen's kappa: `inter_model_agreement_rate`, `grounding_pass_rate`, `audit_flip_rate`, `mandatory_review_flip_rate`. The decision log entry D-019 documents why kappa is not reported here.
- `field_provenance` — list of `FieldLabelProvenance` rows, one per non-default cell.

### Where the raw LLM outputs live

`LabelingProvenance` does **not** store the raw labeler responses or the rendered prompts. Those live in the per-case run artifact under `data/eval_artifacts/labeling/<run_id>/<case_id>.json` (schema described in sparring plan §7). The split keeps `data/gold_standard/housing_v1.jsonl` rows readable and diffable while preserving the full reproducibility trail in a separate, auditable file.

### Invariant: `labeling_provenance is None` semantics

A `None` value means the row predates the auto-label pipeline. The real-gold append gate (`packages/eval/auto_label/append_gate.py`, Phase 6) refuses to append any new real-gold row whose `labeling_provenance` is `None`, so the absence of provenance can only persist for legacy rows already in `housing_v1.jsonl`.


## Determination ontology (housing.repairs_social.v1)

Added 2026-05-06 — see [`docs/eval/housing-ombudsman-determination-ontology-2026-05-06.md`](housing-ombudsman-determination-ontology-2026-05-06.md) for the canonical mapping.

`GroundTruthOutcome` carries (all optional in the schema; required for `housing.repairs_social.v1` rows by INV-D4):

- `determination: Determination | None` — the substantive Ombudsman finding. One of `maladministration`, `severe_maladministration`, `service_failure`, `reasonable_redress`, `no_maladministration`, `resolved_with_intervention`, `outside_jurisdiction`.
- `determination_per_complaint: list[ComplaintFinding]` — per-complaint-head findings for mixed cases (`outcome_raw` contains `;`).
- `amount_ordered_now_gbp: Decimal | None` — fresh binding compensation order (use for `maladministration` / `severe_maladministration` / `service_failure`).
- `amount_previously_offered_gbp: Decimal | None` — landlord pre-existing offer accepted as proportionate (use for `reasonable_redress`).
- `amount_global_unapportioned_gbp: Decimal | None` — settlement total without an apportionment (use for `resolved_with_intervention`).
- `overall_winner_legacy: Winner | None` — backward-compat derived winner. When set, must match `_legacy_winner_for(determination)` (INV-D3).

Invariants:

- **INV-D1** — when any of the three split amount fields is set, their sum equals `total_awarded_gbp` (the unset fields default to None and contribute zero to the sum).
- **INV-D2** — `outside_jurisdiction` requires `total_awarded_gbp == 0` and all split fields None (or `Decimal("0")`).
- **INV-D3** — `overall_winner_legacy`, if set, must match the canonical mapping in `_legacy_winner_for`.
- **INV-D4** — when `domain_id == "housing.repairs_social.v1"`, `ground_truth_outcome.determination` must be set.

Legacy housing.deposit.v1 rows are unaffected — `determination` defaults to None and the additional invariants are vacuously satisfied.

The orchestrator-side mirror enum lives in `packages/llm_orchestrator/models/prediction_v2.py::Determination` (same string values; cross-package conversion handled by `packages/eval/adapter.py::_adapt_determination`).
