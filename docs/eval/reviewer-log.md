# Reviewer Adjudication Log

Track every double-annotation disagreement and its resolution. Required by [SHA-96](https://linear.app/sharifbuilders/issue/SHA-96): Cohen's κ ≥ 0.8 per `claim_type` and a per-disagreement audit trail.

## How to use

When two reviewers annotate the same case and produce different values for the same field, add a row below. **Don't** peek at the other reviewer's labels before re-reading the source PDF.

## Schema

| Date | Case ID | Field | Reviewer A | Reviewer B | Resolution | Rationale |
|---|---|---|---|---|---|---|

## Entries

(empty — populate during Phase 6 double-annotation pass)

## Skipped cases

If a case cannot be annotated (corrupted PDF, withdrawn decision, structurally ambiguous), record it here rather than producing a low-quality annotation.

| Date | Case ID | Reason | Resolution |
|---|---|---|---|

(empty)

## Cohen's κ targets

Computed at end of Phase 6 by `scripts/eval/agreement.py` (lands in Phase 6, not yet implemented).

| `claim_type` | n double-annotated | κ | Status (≥0.8 = pass) |
|---|---|---|---|
| `cleaning` | – | – | – |
| `damages` | – | – | – |
| `deposit_non_protection` | – | – | – |
| `disrepair` | – | – | – |
| `end_of_tenancy` | – | – | – |
