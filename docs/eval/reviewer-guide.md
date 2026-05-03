# Gold-Set Adjudicator Guide

> Workflow for the **adjudicator** confirming LLM-pre-labeled tribunal cases for the Proposer thesis evaluation set.
>
> **Audience:** non-engineer (paralegal or law student). The CLI does not require Python knowledge.
>
> **Replaces** the two-paralegal blind double-annotation flow (SHA-96, superseded by [decision log D-019](../../.sisyphus/notepads/llm-labeling/D-019-llm-assisted-labeling.md) on 2026-05-02).

## TL;DR — the loop

```bash
# 1. The pipeline owner runs auto_label.py first; this writes a per-case
#    artifact under data/eval_artifacts/labeling/<run_id>/<case_id>.json
#    containing both LLM passes, grounding decisions, and the
#    DisagreementSet + MandatoryReviewSet for the case. You don't run this.

# 2. Walk the open cases for a run
python scripts/eval/adjudicate.py list --run-id <run_id>

# 3. Open one case
python scripts/eval/adjudicate.py review --run-id <run_id> --case-id <case_id>

# 4. The CLI presents three queues for THIS case, in order:
#    a) MandatoryReviewSet — every metric-critical cell, even if A and B agreed.
#    b) DisagreementSet     — every cell where A and B differ, OR either is
#                             ungrounded, an invariant fails, or null/non-null
#                             differs.
#    c) Audit overlay       — a deterministic 10% random sample of AGREED
#                             cells, surfaced as a quality check.
#
#    For each row, you see: field path, A's value, B's value, the relevant
#    PDF excerpt, and the grounding-check result. You pick A, B, or type a
#    corrected value, and supply a one-line rationale.

# 5. When the queues are empty, the CLI runs the real-gold append gate
#    (assert_real_gold_appendable). If it passes, the row is appended to
#    data/gold_standard/housing_v1.jsonl. The CLI refuses to append if the
#    gate finds any of: missing labeling_provenance, negative_kind set,
#    missing target_source_id, missing manifest fields, incomplete
#    MandatoryReviewSet, or a missing/mismatched run artifact.
```

That's the whole flow. The rest of this doc explains what each queue surfaces, how to handle ambiguity, and what to do when grounding flags an LLM cell as ungrounded.

## What you're producing

A single adjudicated case ends up as one line in `data/gold_standard/housing_v1.jsonl`. Every row carries a `labeling_provenance` block summarising your decisions, the grounding pass rate, the audit-flip rate, and the hashes needed to replay the labeling later.

The gold set is **research data**. It is the yardstick the thesis is graded against. Adjudication errors propagate into every metric. **Better one careful case than three rushed ones.**

## The three queues, in order

### 1. MandatoryReviewSet — always required, regardless of A/B agreement

The pipeline forces you to confirm every metric-critical cell on every real gold case, even when both LLM labelers agreed. This is the firewall against "LLMs agreed therefore truth." Cells in this queue:

- `facts`
- `disputed_amount_gbp`
- `claim_types`
- `matter_type`
- `ground_truth_outcome.overall_winner`
- `ground_truth_outcome.total_awarded_gbp`
- every `ground_truth_outcome.per_issue[*].winner`
- every `ground_truth_outcome.per_issue[*].awarded_gbp`
- `ground_truth_outcome.unapportioned_reason` (when present)

For each, the CLI shows you the relevant PDF excerpt and asks: does the proposed value match the source? Pick `accept` to keep the proposed value, `correct` to type a different value, or `flag` if the case is structurally bad (corrupted PDF, withdrawn decision).

### 2. DisagreementSet — every cell where A and B differ or either is ungrounded

The auto-grounder rejects cells without a basis span in the source PDF. A cell enters this queue if any of:

- A and B disagree (after canonicalisation)
- Either is `UNGROUNDED` per the auto-grounder
- An invariant fails on either pass
- The basis span is missing
- One pass said `None` and the other did not

Field paths are granular (`evidence[key].kind`, `per_issue[issue=damages].winner`), so list disagreements are not hidden inside list-equality checks. You pick `A`, `B`, or type a corrected value, with a one-line rationale.

### 3. Audit overlay — 10% sample of AGREED cells

A deterministic 10% random sample of cells where A and B agreed is also surfaced. This is the quality audit: do "A and B agreeing" cases actually agree with the source? The resulting flip rate is recorded in `LabelingProvenance.audit_flip_rate` and is the single best operational signal that the LLM pair has a systematic bias.

If you flip an agreed cell during audit, write the rationale carefully — that's a signal Mohamed needs to read.

## Field-by-field guidance

The CLI prefills every value from the LLM passes, but you should still know what each field means.

### `case_id`

Stable, human-readable, unique. Pattern: `<COURT>-<YEAR>-<NUMBER>` (e.g. `FTT-PR-2023-0042`). The append gate refuses duplicates.

### `decision_date`

The date the tribunal issued its decision. ISO format `YYYY-MM-DD`. Must be in `2019-01-01..2024-12-31` (the PILOT window).

### `region` and `region_source`

`region` is one of 12 enum values: `london`, `south_east`, `south_west`, `east_of_england`, `east_midlands`, `west_midlands`, `north_west`, `north_east`, `yorkshire_and_humber`, `wales`, `scotland`, `northern_ireland`.

`region_source` is the verbatim string from the decision PDF.

### `case_size`

Derived from `disputed_amount_gbp`: `small` if ≤ £1500, otherwise `large`. INV-7 enforces this — the LLM pass usually gets it right, but if you correct `disputed_amount_gbp` you must keep `case_size` consistent.

### `disputed_amount_gbp`

The **canonical** disputed amount. Usually the disputed portion of the deposit. Mandatory review.

### `claim_types`

A **list**, not a single value. Multi-type cases list every applicable type. Mandatory review.

### `source_pdf_sha256`

Set by the pipeline from the source PDF; you do not edit this. The append gate verifies it matches the run artifact's `source_pdf_sha256`.

### `parties`

Must include at least one `tenant` and one `landlord`. `agent` is allowed as an additional role. `represented` is `true` if the party appeared with a lawyer or formal representative.

### `facts` — leakage-sensitive

Plain-English summary, drawn ONLY from `pre_decision_record` spans (the parts of the PDF that recount what each party submitted, before the tribunal's reasoning or order). The leakage scanner rejects facts that contain tribunal-finding language ("the tribunal finds", "we award", "we conclude", "we accept the [applicant|respondent]", "judgment for the…", etc.).

If the proposed `facts` text trips the leakage scanner, the CLI surfaces the offending phrase and you rewrite. If you're unsure whether a phrase is decision-language or party-submission language, the rule is: **if it states what the tribunal decided, it does not belong in `facts`**.

### `evidence` and `evidence_unavailable_reason`

Each `Evidence` entry has `kind`, `description`, and an optional `provenance: {page, paragraph}`. Standard kinds: `photo`, `invoice`, `inspection_report`, `tenancy_agreement`, `bank_statement`, `email`, `text_message`, `lease_inventory`.

If the decision lists no evidence, `evidence: []` requires `evidence_unavailable_reason` to be filled.

### `statutory_basis`, `cited_authorities`

The auto-grounder resolves each entry through versioned UK-statutes and BAILII indexes. Entries marked `UNGROUNDED` enter the disagreement queue; you can either correct them or remove them with a rationale.

`cited_date` matters: the temporal-sanity check enforces `cited_date <= decision_date`. A train case (2019–2022) citing a 2024 authority is temporal leakage and the audit rejects it.

### `claimed_amounts`

Per-issue claims. `issue` is a free-text label (`carpet_cleaning`, `damaged_walls`, …). The same `issue` label MUST appear in `ground_truth_outcome.per_issue` for any apportioned outcome.

### `ground_truth_outcome`

The tribunal's actual decision.

- **Apportioned (default):** `per_issue` lists each issue with its winner and award. `total_awarded_gbp` must equal the sum of `per_issue.awarded_gbp`. INV-9 enforces consistency: if all issues went to tenant, `overall_winner` must be `tenant`; if mixed, `overall_winner` must be `split`.
- **Unapportioned:** `unapportioned_reason: "<one sentence>"` is set, `per_issue: []`, and `total_awarded_gbp` stands alone. INV-9 is skipped — you assert `overall_winner` directly.

Mandatory review on every cell here.

### `key_reasoning_quotes`

At least one verbatim quote from the decision. The auto-grounder enforces `match_quote_in_span` against the LLM-emitted span window — quotes that don't ground enter the disagreement queue.

## Common adjudication patterns

| Situation | What to do |
|---|---|
| A and B agree, MandatoryReviewSet cell, you confirm against PDF | `accept` — proposed value carries through |
| A and B agree, audit overlay flips on closer reading | `correct` with the right value, write rationale (audit-flip rate signal) |
| A and B disagree, one is clearly right per the PDF | Pick that one (`A` or `B`) |
| A and B disagree, neither is right | `correct` with the right value |
| Auto-grounder said UNGROUNDED but the value is in the PDF | Look at the span window — the LLM probably claimed the wrong page/paragraph. `correct` with the right span. |
| `facts` trips leakage scanner | Rewrite without tribunal-finding language |
| Both labelers extracted a 2024 authority on a 2021 train case | Temporal leakage; remove the authority unless the tribunal really cited it (rare). Flag to Mohamed if real. |
| Case is structurally bad (corrupt PDF, withdrawn) | `flag` — the row is not appended; record the reason in the reviewer log |

## Human-only anchor set

Before the first 50-case `housing_v1.jsonl` is used for thesis claims, you label a stratified 10–20-case anchor subset **from scratch**, without seeing either LLM output. Use it to defend the calibration claims.

The CLI signals anchor cases with `--anchor` flag. In anchor mode, the LLM passes are not shown until you submit a complete row. The system then logs the divergence between your anchor labels and what the LLM-assisted pipeline would have produced — that's the calibration-defensibility data.

## When you cannot decide

The adjudicator's job is the source of truth on every cell of every real gold row. If after re-reading the PDF you still cannot decide:

1. Open `docs/eval/reviewer-log.md`.
2. Add a row: date, case_id, field path, A's value, B's value, what's ambiguous about the source.
3. Escalate to Mohamed via the row's "Resolution" column. He decides.
4. Update the case to the resolved value via the CLI.

The adjudication log is the audit trail; never silently mark something accepted when the source actually doesn't support either pass.

## Workflow checklist for each case

- [ ] `adjudicate.py list --run-id <run_id>` shows the case as pending
- [ ] `adjudicate.py review --run-id <run_id> --case-id <case_id>` opens the queues
- [ ] **MandatoryReviewSet:** every cell confirmed against source PDF
- [ ] **DisagreementSet:** every cell resolved (`A`, `B`, or `correct`) with rationale
- [ ] **Audit overlay:** every sampled cell either accepted or flipped with rationale
- [ ] `facts` passes the leakage scanner (no tribunal-finding language)
- [ ] `claim_types`, `matter_type`, `ground_truth_outcome` all confirmed against source
- [ ] At least one `key_reasoning_quote` grounded against its span window
- [ ] `decision_date >= max(cited_authorities[*].cited_date)` (temporal sanity)
- [ ] CLI appends successfully (real-gold gate green)
- [ ] Adjudication rationale rows landed in `docs/eval/reviewer-log.md`

## What's recorded in `LabelingProvenance` for this case

When you submit, the CLI records into the row's `labeling_provenance` block:

- `run_id`, `labeled_at`, `labeler_models` (the two providers used)
- Source PDF SHA-256, OCR text SHA-256, prompt template hash, gold-schema hash, corpus manifest hash
- Canonicalizer version, grounder version, audit seed
- `is_human_only_anchor` (true on the stratified anchor subset)
- `human_adjudicator` (your name)
- `adjudicated_fields` (every field path you corrected or confirmed under mandatory review)
- `inter_model_agreement_rate` — raw A/B agreement; **NOT Cohen's κ**, do not present it as one
- `grounding_pass_rate` — share of cells that passed the auto-grounder
- `audit_flip_rate` — share of audited agreed cells you flipped
- `mandatory_review_flip_rate` — share of MandatoryReviewSet cells you corrected
- Per-cell `field_provenance` rows: source, span, match strategy, your one-line rationale where applicable

This block is what makes the gold row reproducible after labeler models or authority indexes drift.

## Reading order

1. This guide (you're here).
2. [`docs/eval/gold-schema.md`](gold-schema.md) — full field-by-field reference with the 10 invariants and the labeling-provenance section.
3. [`docs/eval/reviewer-log.md`](reviewer-log.md) — adjudication log; check it before re-adjudicating a previously-flagged case.
4. [`.sisyphus/notepads/llm-labeling/D-019-llm-assisted-labeling.md`](../../.sisyphus/notepads/llm-labeling/D-019-llm-assisted-labeling.md) — decision log explaining why this flow replaced the two-paralegal protocol.

## Questions / blockers

Slack Mohamed directly. If a case can't be adjudicated for structural reasons (corrupt PDF, withdrawn decision, ambiguous parties), use `flag` in the CLI and the reviewer log under a "Skipped" row; we'll discuss whether to drop it from the corpus.
