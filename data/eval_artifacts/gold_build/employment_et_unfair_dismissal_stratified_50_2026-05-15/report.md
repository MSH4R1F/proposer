# SHA-148 Phase A+B report — ET unfair-dismissal gold-build pre-labeling

**Ticket:** [SHA-148 / SHA-65d](https://linear.app/sharifbuilders/issue/SHA-148)
**Date:** 2026-05-15
**Branch:** `feature/sha-148-sha-65d-stratified-50-case-reviewed-gold-for` (off SHA-147)
**Corpus source:** [`data/eval_artifacts/corpus/employment_et_unfair_dismissal_v1_2026-05-15.jsonl`](../../corpus/employment_et_unfair_dismissal_v1_2026-05-15.jsonl) (1000 docs, SHA-147)

## What this PR ships

Phases A + B of the SHA-148-full plan: stratified selection of 50 unfair-dismissal cases plus PDF download + text extraction for each. The redacted PDF text is the input that Phase C (LLM-panel labeling) will consume.

This PR does **not** append any rows to `data/gold_standard/employment_unfair_dismissal_v1.jsonl` — gold promotion is Phase D after human review.

## Phase A — stratified selection

[`build_employment_et_unfair_dismissal_stratified_eval.py`](../../../../scripts/eval/build_employment_et_unfair_dismissal_stratified_eval.py) deterministically sampled 50 cases from the 1000-doc SHA-147 corpus.

### Stratification axes

1. **Country** — proportional to corpus (897 E&W / 103 Scotland → 44 / 6 in n=50, with a floor of 1 per non-empty stratum).
2. **Decision-date quartile** — empirical quartiles of the corpus's decision-date distribution, NOT calendar quarters. The corpus is heavily skewed to 2025-2026 so the quartile edges land at `2025-11-14`, `2025-12-31`, `2026-02-12`.
3. **Jurisdiction-code breadth** — single `Unfair Dismissal` rows preferred over combined-claims pages. With seed=42 all 50 selected rows are single-UD.

### Selected distribution

| Country | Q1 ≤2025-11-14 | Q2 ≤2025-12-31 | Q3 ≤2026-02-12 | Q4 >2026-02-12 | Total |
|---|---:|---:|---:|---:|---:|
| England & Wales | ~10 | ~12 | ~12 | ~10 | 44 |
| Scotland | ~2 | ~1 | ~1 | ~2 | 6 |
| **Total** | **12** | **13** | **13** | **12** | **50** |

(Exact per-cell counts are deterministic given seed=42 and the empirical quartile edges; see [`selection_summary.json`](selection_summary.json) for the canonical breakdown.)

### Reproducibility

```bash
PYTHONPATH=packages venv/bin/python -m scripts.eval.build_employment_et_unfair_dismissal_stratified_eval \
    --seed 42 --size 50
```

Selection is content-hash-stable: re-running with the same `--seed` against the same corpus manifest yields the same 50 rows.

### Output

- [`selection_manifest.jsonl`](selection_manifest.jsonl) — 50 rows, each carrying:
  - case identifiers (`case_reference`, `case_numbers`, `source_url`, `base_path`)
  - decision metadata (`decision_date`, `country`, `jurisdiction_codes`)
  - `first_attachment` (the PDF URL Phase B downloads)
  - SHA-20 Phase 7 fields pre-populated (`domain_id`, `forum`, `source_publisher`, `source_kind`, `retrieval_namespace_id`, `corpus_version`, `matter_type`)
  - `annotation_status: needs_pdf_extraction`
- [`selection_summary.json`](selection_summary.json) — selection stats + reproducibility manifest

## Phase B — PDF download + text extraction

[`build_employment_et_unfair_dismissal_pdf_extraction.py`](../../../../scripts/eval/build_employment_et_unfair_dismissal_pdf_extraction.py) reads `selection_manifest.jsonl` and for each row: downloads the first PDF attachment at 1 rps, extracts text via [`rag_engine.extractors.pdf_extractor.PDFExtractor`](../../../../packages/rag_engine/extractors/pdf_extractor.py) (PyMuPDF 1.26.5), applies the existing employment-tribunal PII redactor, and persists per-case artifacts beside the SHA-147 HTML body.

### Results

| Metric | Value |
|---|---|
| PDFs targeted | 50 |
| **PDFs successfully extracted** | **50** |
| Failures | 0 |
| Total runtime | ~51 s |
| Effective fetch rate | ~1.0 rps |
| Total PDF bytes | 10.6 MB |
| Median pages per PDF | 2 |
| Page range | 1 to 18 |
| Median redacted-text chars per PDF | 1725 |
| Redacted-text range | ~770 to ~43,000 chars |

The 1-page / sub-1000-char PDFs are the cover-judgment-only pattern: a short reserved-judgment cover page with the substantive reasoning in a separate `Reasons` PDF that GOV.UK does not always link from the landing page. Phase C will need to handle this — either follow `Reasons` links if present, or accept that some gold rows label the cover only. Flag for SHA-148 Phase C scope.

### Redaction summary (across 50 PDFs)

| Redactor | Hits |
|---|---:|
| Postcodes | 1 (real PII GOV.UK upstream missed — caught by our defence-in-depth) |
| Phone (no-space) | 0 |
| Phone (spaced UK mobile) | 0 |
| Emails | 0 |
| NI numbers | 0 |
| Bank-details placeholder | 10 hits across 2 cases (likely false-positive digit-cluster matches in the upstream `TextCleaner` regex; redacted-to-placeholder is still safe) |

### PII regression sweep

Independent scan over every committed redacted PDF text:

| Pattern | Hits |
|---|---:|
| UK postcode | 0 |
| UK phone (no-space) | 0 |
| UK phone (spaced) | 0 |
| Email | 0 |
| NI number | 0 |

**Zero unredacted PII across all 50 committed PDF texts.** Confirms the redactor closes the gap on the one postcode the upstream pre-publication redaction missed.

### Per-case artifacts (gitignored, working layout)

Under `data/raw/employment/decisions/<case_ref>/`:

```
attachments/<filename>.pdf       # raw PDF bytes
pdf_text_raw.txt                  # extracted text pre-redaction
pdf_text_redacted.txt             # model-facing text (input to Phase C)
pdf_metadata.json                 # extraction + redaction stats
```

These are intentionally NOT committed — they are sensitive publisher content. The committed `pdf_extraction_report.jsonl` carries `text_head` / `text_tail` excerpts (~240 chars each) plus the SHA-256 of the source PDF for spot-check and reproducibility.

### Output

- [`pdf_extraction_report.jsonl`](pdf_extraction_report.jsonl) — 50 rows (one per case) with download status, PDF SHA-256, extraction stats, redaction stats, head/tail excerpts
- [`pdf_extraction_summary.json`](pdf_extraction_summary.json) — aggregated stats

## What's NOT done (Phase C + D, future session)

| Phase | What's needed |
|---|---|
| **C** | Employment-domain prompt pack under `packages/llm_orchestrator/prompts/employment_et_unfair_dismissal_v1/` covering extraction of `claim_types`, `parties`, `ground_truth_outcome` (incl. ET-specific remedy fields), `key_reasoning_quotes`, `statutory_basis`, and the SHA-149 factor surfaces. Adapter in `packages/eval/auto_label/` aware of the ET schema (SHA-144). LLM-panel double-pass run via `scripts/eval/auto_label.py` — needs API budget (~£5-10 for 50 × 2 providers × 4-5 prompts). |
| **D** | Mandatory human review of `claim_types`, `ground_truth_outcome.overall_winner`, `total_awarded_gbp` / remedy components, `key_reasoning_quotes`, `matter_type`, fair-reason category, country. Promote via `assert_real_gold_appendable` to `data/gold_standard/employment_unfair_dismissal_v1.jsonl`. |

## Files committed in this checkpoint

- [`scripts/eval/build_employment_et_unfair_dismissal_stratified_eval.py`](../../../../scripts/eval/build_employment_et_unfair_dismissal_stratified_eval.py) (new)
- [`scripts/eval/build_employment_et_unfair_dismissal_pdf_extraction.py`](../../../../scripts/eval/build_employment_et_unfair_dismissal_pdf_extraction.py) (new)
- [`data/eval_artifacts/gold_build/employment_et_unfair_dismissal_stratified_50_2026-05-15/selection_manifest.jsonl`](selection_manifest.jsonl)
- [`data/eval_artifacts/gold_build/employment_et_unfair_dismissal_stratified_50_2026-05-15/selection_summary.json`](selection_summary.json)
- [`data/eval_artifacts/gold_build/employment_et_unfair_dismissal_stratified_50_2026-05-15/pdf_extraction_report.jsonl`](pdf_extraction_report.jsonl)
- [`data/eval_artifacts/gold_build/employment_et_unfair_dismissal_stratified_50_2026-05-15/pdf_extraction_summary.json`](pdf_extraction_summary.json)
- This report
