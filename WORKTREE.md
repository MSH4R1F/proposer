# WORKTREE — SHA-146 / SHA-65b: Live 30-doc ET unfair-dismissal pilot scrape

**Linear**: [SHA-146](https://linear.app/sharifbuilders/issue/SHA-146) (logical name SHA-65b; child of [SHA-65](https://linear.app/sharifbuilders/issue/SHA-65)).
**Branch**: `feature/sha-146-sha-65b-live-30-doc-et-unfair-dismissal-pilot-scrape`
**Created**: 2026-05-14, branched off `feature/sha-145-sha-65a-employment-tribunal-scraper-code` (the scraper PR is not merged yet).
**Design spec**: [`docs/superpowers/specs/2026-05-13-employment-tribunal-vertical-design.md`](../../docs/superpowers/specs/2026-05-13-employment-tribunal-vertical-design.md) §4 (SHA-65b row), §5.2
**Sibling tickets**: SHA-145 ✅ (scraper, in this branch's parent) · SHA-144 ✅ (schema gate) · SHA-147 (full scrape, gated on this pilot) · SHA-148 · SHA-149 · SHA-150

## What this worktree owns

Run the SHA-145 scraper against the live GOV.UK Employment Tribunal listing at `https://www.gov.uk/employment-tribunal-decisions?tribunal_decision_categories=unfair-dismissal`. Capture ~30 kept decisions plus an excluded manifest. **Validate parser fidelity, model-facing PII redaction, and the two-stage filter against real HTML** — this is the gate before SHA-147 (the 1000-doc scrape).

**User-set rate**: 2.0 rps (overriding the spec default of 0.5 rps). Still well within polite territory for a major government site (GOV.UK serves orders of magnitude more traffic than this).

## Files allowed

- `data/eval_artifacts/pilots/employment_et_unfair_dismissal_pilot_30_<date>.jsonl` (kept manifest)
- `data/eval_artifacts/pilots/employment_et_unfair_dismissal_pilot_30_<date>_excluded.jsonl` (rejected manifest)
- `data/eval_artifacts/pilots/employment_et_unfair_dismissal_pilot_30_<date>_report.md` (pilot report)
- Working artifacts created by the scraper under `data/raw/employment/` are gitignored (per `.gitignore:279`).

## Files forbidden

- `scripts/scrapers/employment_tribunal/**` — code lives in SHA-145, not modified here
- `packages/eval/schema.py` — owned by SHA-144
- `apps/**`, `packages/**` — other tracks

## DoD (from SHA-146 ticket)

- [ ] Live pilot run captured 25-30 kept decisions (gate: ≥25 or escalate)
- [ ] PII regression sweep on every committed `source_document.json` shows zero leakage of postcode / phone (spaced or no-space) / email / NI number / bank pattern (gate: ≤15% leakage or halt before SHA-147)
- [ ] Two-stage filter spot-check: 5 accepted + 5 rejected rows reviewed; reason codes match the body content
- [ ] Content-hash dedup confirmed (no duplicate `source_id` in `master_index.json`)
- [ ] Robots.txt response captured in pilot report
- [ ] Pilot report summarises: kept count, excluded count by reason, parser issues, PII findings, ratio of merits judgments to preliminary/strike-out — early signal for SHA-147 viability

## Out of scope

- Code changes to the scraper (those belong in SHA-145 follow-ups).
- Vector/BM25 ingestion (SHA-147).
- Gold-set generation (SHA-148).

## Notes

- Branched **off** the SHA-145 PR's branch (not main). When SHA-145 merges, this branch will need a rebase. That's intentional: SHA-146 needs the scraper code to exist somewhere.
- Project venv at `legal-mediation-system/venv/`. Use `venv/bin/python -m scripts.scrapers.employment_tribunal.govuk_scraper …` — never the system python.
