# Gold-Set Reviewer Guide

> Workflow for the paralegal/law-student reviewer annotating tribunal decisions for the Proposer thesis evaluation set. **Audience:** non-engineer. The CLI does not require Python knowledge.

## TL;DR — the loop

```bash
# 1. Pick a tribunal decision PDF from data/raw/bailii/
# 2. Compute its SHA-256
sha256sum data/raw/bailii/your_case.pdf

# 3. Get a starter JSON file
python scripts/eval/annotate.py template > my_case.json

# 4. Open my_case.json in your editor and replace every REPLACE_ME placeholder
#    plus the 0-amount values, plus the source_pdf_sha256.

# 5. Validate
python scripts/eval/annotate.py validate my_case.json

# 6. When validate is clean, append to the corpus
python scripts/eval/annotate.py append my_case.json
```

That's the whole flow. The rest of this doc explains each field, how to handle ambiguity, and what to do when two reviewers disagree.

## What you're producing

A single annotated case ends up as one line in `data/gold_standard/housing_v1.jsonl`. Every case is the same shape; the schema is in `packages/eval/schema.py` (you don't need to read it — `template` gives you the structure).

The gold set is **research data**. It teaches the model what "good" looks like, and is the yardstick the thesis is graded against. Annotation errors propagate into every metric. **Better one slow accurate case than three rushed ones.**

## Picking cases

Don't cherry-pick. The 50-case corpus must be **stratified**:

| Dimension | Target |
|---|---|
| Claim types | ≥ 5 cases per type — `cleaning`, `damages`, `deposit_non_protection`, `disrepair`, `end_of_tenancy`. Multi-type cases count toward each of their types. |
| Dates | Train 2019–2022 (≈ 35 cases) + Test 2023–2024 (≈ 15 cases). Roughly the PILOT 70/30 split. |
| Regions | London should be ~30%, rest of UK ~70%. |
| Case size | Small (≤ £1500 disputed) ~30%, Large (> £1500) ~70%. |

Mohamed will hand you a tracking spreadsheet listing which slots remain open. Don't worry about hitting the targets exactly — get the cases done; the audit (`python -m eval.dataset audit data/gold_standard/housing_v1.jsonl`) will report any imbalance and we adjust the next batch.

## Field-by-field guidance

The starter `template` includes every field. This section explains the non-obvious ones.

### `case_id`

Stable, human-readable, unique. Pattern: `<COURT>-<YEAR>-<NUMBER>` (e.g. `FTT-PR-2023-0042`). The CLI refuses duplicates on `append`, so once committed, never reuse.

### `decision_date`

The date the tribunal issued its decision. ISO format `YYYY-MM-DD`. Must be in `2019-01-01..2024-12-31` (the PILOT window).

### `region` and `region_source`

`region` is one of 12 enum values: `london`, `south_east`, `south_west`, `east_of_england`, `east_midlands`, `west_midlands`, `north_west`, `north_east`, `yorkshire_and_humber`, `wales`, `scotland`, `northern_ireland`.

`region_source` is the verbatim string from the decision PDF. For a decision that says "Greater London" you'd record `"region": "london", "region_source": "Greater London"`. The schema audit uses `region`; `region_source` is for provenance only.

### `case_size`

Derived from `disputed_amount_gbp`: `small` if ≤ £1500, otherwise `large`. The schema cross-checks; if you set them inconsistently the CLI fails.

### `disputed_amount_gbp`

The **canonical** disputed amount. Usually the disputed portion of the deposit, e.g. if the tenant paid £1200 and the landlord retained £400 disputed by the tenant, this is £400 — not £1200, not the sum of both parties' positions in `claimed_amounts`.

### `claim_types`

A **list**, not a single value. A case where the landlord deducted for cleaning AND damages is `["cleaning", "damages"]`. Pick all that apply.

### `source_pdf_sha256`

The SHA-256 hash of the source PDF, lowercase hex, 64 chars. From the terminal:

```bash
sha256sum data/raw/bailii/your_case.pdf
```

Lets reviewer B re-fetch and re-OCR independently and confirm they're looking at the same source.

### `ocr_confidence`

If the PDF was processed via OCR and you have a confidence number, record it (0–1). If the PDF is text-native or you don't have a confidence, set `null`.

### `parties`

Must include at least one `tenant` and one `landlord`. `agent` is allowed as an additional role. `represented` is `true` if the party appeared with a lawyer or formal representative.

### `facts`

Plain-English summary. Minimum 50 characters. Aim for 2–4 sentences:

> "Tenant occupied a 2-bed flat from 2022-01-01 to 2023-05-31. Landlord retained £400 of the £1200 deposit, citing carpet damage and cleaning costs. Tenant disputed the deduction, arguing fair wear and tear."

Don't paste the tribunal's own summary verbatim — that's likely too long and may be biased. Write a neutral 1-paragraph summary in your own words.

### `evidence` and `evidence_unavailable_reason`

Each `Evidence` entry has `kind`, `description`, and an optional `provenance: {page, paragraph}`. Evidence kinds are free text but should be standard: `photo`, `invoice`, `inspection_report`, `tenancy_agreement`, `bank_statement`, `email`, `text_message`, `lease_inventory`.

If the decision **lists no evidence** (rare but happens — e.g. submissions-only hearings), set `evidence: []` and fill `evidence_unavailable_reason` with one sentence explaining why. The schema rejects empty evidence without a reason — the rule is: be deliberate, never silent.

### `statutory_basis` and `statutory_basis_unavailable_reason`

Same pattern. Standard statutes you'll see:

- Housing Act 2004 s.213 (deposit protection)
- Housing Act 2004 s.214 (penalty for non-protection)
- Tenant Fees Act 2019 s.1 (prohibited payments)
- Landlord and Tenant Act 1985 s.11 (repair obligations)

If the decision turns purely on common-law principles (rare in tribunal cases), set `statutory_basis: []` with a reason.

### `cited_authorities`

Case-law authorities the tribunal cites. Each has `name`, `cited_date` (the **cited** authority's decision date, not this case's), optional `court` and `provenance`. Empty list is fine — many tribunal decisions cite no authorities.

`cited_date` matters: a 2021 train case citing a 2024 authority is **temporal leakage** — flagged by the audit. Don't lie about dates to avoid the warning; if the tribunal really did cite a future authority (impossible in practice), record it accurately and flag to Mohamed.

### `claimed_amounts`

Per-issue claims. `issue` is a free-text label (e.g. `"carpet_cleaning"`, `"damaged_walls"`). The same `issue` label MUST appear in `ground_truth_outcome.per_issue` for any apportioned outcome. Use `snake_case` and be consistent across cases.

### `ground_truth_outcome`

The judge's actual decision.

- **Apportioned (default):** `per_issue` lists each issue with its winner and award. `total_awarded_gbp` must equal the sum of `per_issue.awarded_gbp`. INV-9 enforces consistency: if all issues went to tenant, `overall_winner` must be `tenant`; if mixed, `overall_winner` must be `split`.
- **Unapportioned:** the tribunal gave a global figure with no breakdown. Set `unapportioned_reason: "<one sentence>"` and leave `per_issue: []`. `total_awarded_gbp` stands alone. INV-9 is skipped — you assert `overall_winner` directly.

If you're unsure which path applies, read the tribunal's reasoning paragraph 3 times. If it lists individual amounts per issue → apportioned. If it gives one global number with rationale "weighing all factors" → unapportioned.

### `key_reasoning_quotes`

At least one verbatim quote from the decision that captures the tribunal's central reasoning. Each requires `provenance: {page, paragraph}` so reviewer B can locate and verify the quote.

> Aim for 1–3 quotes per case. The right quote is usually one that begins with "I find that…" or "The tribunal concludes…".

## Common mistakes

| Mistake | Why it's wrong | What to do instead |
|---|---|---|
| Copying the tribunal's headnote into `facts` | Headnotes are written by court staff, not neutral, and often summarise badly | Write your own 1-paragraph neutral summary |
| Using "London" (capitalised) in `region` | The enum is lowercase | Use `"london"`; capture "London" in `region_source` |
| Forcing a single `claim_type` on a multi-type case | Lossy; the audit miscounts | List every type that applies, e.g. `["cleaning", "damages"]` |
| Setting `case_size: "large"` on a £400 dispute | INV-7 rejects it | Match `case_size` to `disputed_amount_gbp` (≤ £1500 → small) |
| Fabricating a `provenance.paragraph` you couldn't actually find | Reviewer B will spot it | Leave optional provenance off if unsure; use `null` |
| Setting `unapportioned_reason` AND filling `per_issue` | Schema rejects this | Pick one path. Apportioned (per-issue) is the default. |
| Putting a 2024 authority in a 2021 train case | Temporal leakage | If the tribunal really cited it (rare), record honestly and flag to Mohamed |

## When you and the second reviewer disagree

Per [SHA-96](https://linear.app/sharifbuilders/issue/SHA-96), at least 10% of cases get blind double annotation, and we report Cohen's κ ≥ 0.8 per claim type. When you disagree:

1. Don't peek at the other reviewer's labels. Re-read the source PDF first.
2. If after re-reading you still disagree, open `docs/eval/reviewer-log.md`.
3. Add a row: date, case_id, the field in dispute, both reviewer's choices, and a brief description of the disagreement.
4. Escalate to Mohamed via the row's "Resolution" column. He decides.
5. Update the case to the resolved value. Append using `annotate.py append` (the duplicate-id check will reject the second reviewer's annotation; that's fine — only the resolved version goes in).

## Workflow checklist for each case

- [ ] PDF picked from `data/raw/bailii/`
- [ ] SHA-256 computed
- [ ] `annotate.py template > draft.json` run
- [ ] Every `REPLACE_ME` replaced
- [ ] `disputed_amount_gbp` and `case_size` consistent (small ≤ £1500)
- [ ] `claim_types` lists every type that applies
- [ ] `parties` includes a tenant and a landlord
- [ ] `facts` is your own ≥50-char summary
- [ ] `evidence` non-empty OR `evidence_unavailable_reason` set
- [ ] `statutory_basis` non-empty OR reason set
- [ ] `cited_authorities` filled (empty list OK if none cited)
- [ ] `ground_truth_outcome` apportioned-or-unapportioned correctly
- [ ] At least one `key_reasoning_quote` with `provenance.page` and `provenance.paragraph`
- [ ] `annotate.py validate draft.json` returns "Valid."
- [ ] `annotate.py append draft.json` returns "Appended <case_id>"

## Reading order

1. This guide (you're here).
2. [`docs/eval/gold-schema.md`](gold-schema.md) — full field-by-field reference with the 10 invariants.
3. [`docs/eval/reviewer-log.md`](reviewer-log.md) — adjudication log; check it before re-annotating a disputed case.

## Questions / blockers

Slack Mohamed directly. If a case can't be annotated for structural reasons (corrupted PDF, withdrawn decision, ambiguous parties), record the case_id and the reason in the reviewer log under a "Skipped" row; we'll discuss whether to drop it from the corpus.
