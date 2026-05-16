# WORKTREE — SHA-148 / SHA-65d: ET unfair-dismissal stratified 50-case gold set

**Linear**: [SHA-148](https://linear.app/sharifbuilders/issue/SHA-148) (logical name SHA-65d; child of [SHA-65](https://linear.app/sharifbuilders/issue/SHA-65)).
**Branch**: `feature/sha-148-sha-65d-stratified-50-case-reviewed-gold-for`
**Created**: 2026-05-15, branched off `feature/sha-147-…@35d6a182` (the 1000-doc corpus).
**Design spec**: [`docs/superpowers/specs/2026-05-13-employment-tribunal-vertical-design.md`](../../docs/superpowers/specs/2026-05-13-employment-tribunal-vertical-design.md) §4 (SHA-65d row), §5.3
**Predecessors**: SHA-144 ✅ schema · SHA-145 ✅ scraper · SHA-146 ✅ pilot · SHA-147 ✅ corpus
**Pattern reference**: SHA-127 (housing.repairs_social.v1 stratified-50 gold)

## What this worktree owns

Produce `data/gold_standard/employment_unfair_dismissal_v1.jsonl` with ≥50 reviewed-gold rows for `employment.et.unfair_dismissal.v1`. This is the SHA-148-full path the user picked on 2026-05-15: PDF download + text extraction lives **inside** this worktree, not as a separate SHA-145 followup.

### Phased plan (this is a multi-session ticket)

| Phase | Scope | Session |
|---|---|---|
| **A** | Stratified selection of ~50 cases from the SHA-147 1000-doc corpus (axes: country, decision-date quartile, jurisdiction codes). Output: `data/eval_artifacts/gold_build/employment_et_unfair_dismissal_stratified_50_<date>/selection_manifest.jsonl`. | **This session** |
| **B** | PDF download + text extraction for the 50 selected cases. Reuse `rag_engine.extractors.pdf_extractor.PDFExtractor` per the design spec. PII redaction wired through the existing `to_source_document.redact_model_facing_text`. Output: per-case `pdf_text.txt` + an enriched `source_document.json` carrying the PDF text. | **This session** |
| **C** | LLM-panel labeling (per memory `llm_panel_review_substitutes_paralegal`): two providers extract outcome / fair-reason / award fields / per-issue findings against the PDF text. Requires: employment-domain prompt pack (does not exist yet), API budget (~£5-10 for 50 × 2 × 4-5 prompts), `packages/eval/auto_label/` adapter for ET. | **Future session** |
| **D** | Mandatory human review of: `claim_types`, `ground_truth_outcome.overall_winner`, `total_awarded_gbp` (or remedy components), `key_reasoning_quotes`, `matter_type`, fair-reason category, country. Promote to gold via `assert_real_gold_appendable`. | **Future session** |

This session ends at a clean PR checkpoint after Phase B. Phase C/D land on a follow-up PR off this branch.

## Files allowed

- `scripts/eval/build_employment_et_unfair_dismissal_stratified_eval.py` (Phase A, new)
- `scripts/eval/build_employment_et_unfair_dismissal_pdf_extraction.py` (Phase B, new)
- `data/eval_artifacts/gold_build/employment_et_unfair_dismissal_stratified_50_<date>/**` (committed selection manifest + review packet)
- Working artifacts under `data/raw/employment/decisions/<case_ref>/attachments/` are gitignored per `.gitignore:279`

## Files forbidden

- `scripts/scrapers/employment_tribunal/**` — code in SHA-145 branch (read-only)
- `packages/eval/schema.py` — schema in SHA-144 branch (read-only)
- `data/gold_standard/employment_unfair_dismissal_v1.jsonl` — **not appended in Phase A/B**; appended in Phase D after human review
- `apps/**` — other tracks

## DoD checkpoint after Phase B (this session)

- [ ] Selection manifest with ~50 cases covering country / decision-date quartile / jurisdiction codes
- [ ] PDFs downloaded for all 50 selected cases (at 1 rps per ticket §8.6 — be polite during a deliberate human-curation pass)
- [ ] PDF text extracted, PII-redacted, persisted alongside HTML body
- [ ] PII regression sweep across PDF text (gate: zero leaks of postcode/phone/email/NI/bank)
- [ ] Stage-2 filter still applied — if a PDF reveals the case is e.g. a discrimination-led judgment, downstream selection drops it
- [ ] PR description + report committed under `data/eval_artifacts/gold_build/.../report.md` listing: selection rationale, PDF download stats, parser issues, PII findings

## DoD remaining for Phase C+D (next session)

- [ ] Employment prompt pack at `packages/llm_orchestrator/prompts/employment_et_unfair_dismissal_v1/` covering extraction + adjudication
- [ ] LLM-panel double-pass run logged under `data/eval_artifacts/labeling/<run-id>/`
- [ ] Mandatory human review checklist in a separate session
- [ ] Append 50 reviewed-gold rows to `data/gold_standard/employment_unfair_dismissal_v1.jsonl`
- [ ] All rows satisfy `assert_real_gold_appendable` and validate against the SHA-144 schema (INV-2 family-aware, INV-D5 determination required, INV-F1 forum coherence)

## Notes

- Project venv at `legal-mediation-system/venv/`.
- SHA-147 corpus skews 2023-2026 (97% in 2025-2026). Train/test split target for SHA-65f shifts accordingly — see SHA-147 report §"Recommendation for SHA-148" for two split options.
- The HTML-only doc bodies have `outcome_normalized=None` everywhere (SHA-146 finding). All outcome / fair-reason / award labels for gold rows MUST come from PDF text.
