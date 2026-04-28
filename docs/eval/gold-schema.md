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
| `region` | string | Free text region label, e.g. `"London"`, `"North West"`, `"Wales"`. Used for the 30/70 stratification audit. |
| `case_size` | enum `CaseSize` | `"small"` if total claimed ≤ £1500, otherwise `"large"`. Cross-validated against `claimed_amounts`. |
| `claim_types` | list of enum `ClaimType`, ≥1 | One or more of `cleaning`, `damages`, `deposit_non_protection`, `disrepair`, `end_of_tenancy`. Multi-type cases are common (a single decision can hit cleaning + damages + disrepair). Stratification target ("≥5 cases per claim type") is computed as: for each type `t`, `t in case.claim_types` for ≥5 cases. See [SHA-92](https://linear.app/sharifbuilders/issue/SHA-92). |
| `source_pdf_sha256` | string | 64-char lowercase hex — SHA-256 of the source tribunal PDF. Lets reviewers re-fetch and re-OCR independently. |
| `ocr_confidence` | float ∈ [0,1] or `null` | OCR confidence of the source extraction; `null` when source is text-native. |
| `parties` | list of `Party` | At least one `tenant` and one `landlord`. `agent` permitted as third role. |
| `facts` | string, ≥50 chars | Plain-English summary of the dispute. |
| `evidence` | list of `Evidence` | Discrete pieces of evidence relied on by the tribunal. |
| `statutory_basis` | list of `StatutoryReference` | Statutes cited by the decision. |
| `cited_authorities` | list of `Authority`, default `[]` | Case-law authorities cited by the tribunal. Empty list permitted (some decisions cite none). Phase 2 `dataset.audit()` uses this for the temporal-leakage check: a training case must not cite an authority decided after the train-window cutoff. See [SHA-90](https://linear.app/sharifbuilders/issue/SHA-90). |
| `claimed_amounts` | list of `ClaimedAmount`, ≥1 | Each is `(issue, amount_gbp, by_party)`. The `issue` field is a free-text label that **must match** the `issue` on every `IssueOutcome` in `ground_truth_outcome.per_issue` (INV-5). |
| `ground_truth_outcome` | `GroundTruthOutcome` | The judge's actual decision. |
| `key_reasoning_quotes` | list of `ReasoningQuote`, ≥1 | Quotes lifted from the decision text. Every quote must carry a `paragraph_ref` so reviewers can locate it in the source PDF. |

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
| `paragraph_ref` | string or `null` | Where in the decision PDF this evidence is discussed. |

### `StatutoryReference`

| Field | Type |
|---|---|
| `statute` | e.g. `"Housing Act 2004"` |
| `section` | e.g. `"s.213"` |
| `paragraph_ref` | optional |

### `Authority`

| Field | Type | Notes |
|---|---|---|
| `name` | string, non-empty | e.g. `"Howard de Walden Estates Ltd v Aggio"`. |
| `court` | string or `null` | e.g. `"UKSC"`, `"EWCA Civ"`, `"FTT(PC)"`. |
| `cited_date` | ISO date | Decision date of the **cited** authority (not of the current case). Used by the temporal-leakage audit. |
| `paragraph_ref` | string or `null` | Where in the *current* decision this authority is cited. |

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

| Field | Type | Notes |
|---|---|---|
| `overall_winner` | `tenant` / `landlord` / `split` | The headline outcome. |
| `total_awarded_gbp` | `Decimal`, ≥0 | **Must equal** `sum(per_issue[].awarded_gbp)` exactly (Decimal). |
| `per_issue` | list, ≥1 | Per-issue decomposition. |

### `ReasoningQuote`

| Field | Type | Notes |
|---|---|---|
| `text` | string, ≥1 char | Verbatim quote from decision. |
| `paragraph_ref` | string, ≥1 char | **Required** — every quote must be locatable in source PDF. |

## Cross-field invariants

These are enforced by `@model_validator(mode="after")` on `GoldCase` (and `GroundTruthOutcome` for INV-6). Field-level constraints (`Field(ge=0)`, `min_length=...`) are enforced inline.

| ID | Rule | Where enforced | Why |
|---|---|---|---|
| INV-1 | `decision_date` in `[2019-01-01, 2024-12-31]` | `GoldCase` | PILOT temporal-split window. Case outside window is either training-set leakage or out-of-distribution. |
| INV-2 | `parties` includes ≥1 `tenant` and ≥1 `landlord` | `GoldCase` | A deposit-dispute case without both parties is an annotation error. |
| INV-3 | `ocr_confidence` ∈ `[0,1]` when set; `null` allowed | `Field(ge=0, le=1)` on `GoldCase` | Sanity check on OCR pipeline output; `null` lets text-native PDFs bypass. |
| INV-4 | `source_pdf_sha256` matches `^[0-9a-f]{64}$` | `GoldCase` | Stops typos and accidental UPPERCASE; reviewer can recompute and confirm. |
| INV-5 | Every `ground_truth_outcome.per_issue[].issue` appears in `claimed_amounts[].issue` | `GoldCase` | The judge cannot decide an issue that no party claimed; mismatch is an annotation drift between the two lists. |
| INV-6 | `ground_truth_outcome.total_awarded_gbp` == `sum(per_issue[].awarded_gbp)` (Decimal exact) | `GroundTruthOutcome` | Catches arithmetic typos at annotation time. |
| INV-7 | `case_size == small` iff `sum(claimed_amounts[].amount_gbp) <= £1500` | `GoldCase` | The 30/70 stratification audit is run from the corpus alone. If `case_size` lies, the audit silently breaks. |
| INV-8 | `Decimal` amounts never negative | `Field(ge=0)` on `ClaimedAmount`, `IssueOutcome`, `GroundTruthOutcome` | Tribunal awards cannot be negative; negative values are sign errors. |

## Canonical example

```json
{
  "schema_version": "v1",
  "case_id": "SYNTH-2023-0001",
  "decision_date": "2023-06-15",
  "region": "London",
  "case_size": "small",
  "claim_types": ["cleaning"],
  "source_pdf_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "ocr_confidence": 0.92,
  "parties": [
    {"role": "tenant", "represented": false},
    {"role": "landlord", "represented": true}
  ],
  "facts": "Tenant occupied flat from 2022-01-01 to 2023-05-31; landlord retained 400 GBP of the 1200 GBP deposit citing carpet cleaning and disputed the deduction.",
  "evidence": [
    {"kind": "invoice", "description": "Carpet cleaning invoice for 180 GBP", "paragraph_ref": "para 7"}
  ],
  "statutory_basis": [
    {"statute": "Housing Act 2004", "section": "s.213", "paragraph_ref": "para 12"}
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
    {"text": "The landlord adduced no evidence beyond a single invoice.", "paragraph_ref": "para 14"}
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

- `region` is free text. Once we have ≥30 cases we should normalise to a closed enum.
<!-- (former `claim_type` single-valued limitation resolved in SHA-92) -->
- `evidence.kind` is free text — same closed-enum question as `region`.
- Per-party representation captured as a single bool; reviewer noted that "self-represented but with paid McKenzie friend" is a real category. Defer until corpus shows ≥5 such cases.

These limitations are surfaced in the Codex sparring template at `.sisyphus/codex/sha-28-schema-2026-04-27.md`.
