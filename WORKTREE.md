# WORKTREE — SHA-144 / SHA-65-0: Employment gold-schema readiness gate

**Linear**: [SHA-144](https://linear.app/sharifbuilders/issue/SHA-144) (logical name SHA-65-0; child of [SHA-65](https://linear.app/sharifbuilders/issue/SHA-65)).
**Branch**: `feature/sha-144-sha-65-0-employment-gold-schema-readiness-gate`
**Created**: 2026-05-14 off `main@be8cb3a8`.
**Design spec**: [`docs/superpowers/specs/2026-05-13-employment-tribunal-vertical-design.md`](../../docs/superpowers/specs/2026-05-13-employment-tribunal-vertical-design.md) §5.3, §8.1
**User decision (2026-05-14)**: **Option 1 — extend `GoldCase` enums** (additive). Spec §8.1 had recommended option 2 (domain-specific adapter); user overrode in favour of a single schema with forum-coercion guards.
**Sibling tickets**: SHA-145 ✅ (scraper, done) · SHA-146 (pilot) · SHA-147 (full scrape) · SHA-148 (gold) · SHA-149 (factor catalog) · SHA-150 (evals)

## What this worktree owns

Resolve the housing-shaped enum mismatch that currently blocks `employment.et.unfair_dismissal.v1` gold append. Extend existing enums + invariants additively, add forum-coercion guards, and add ET remedy fields to `GroundTruthOutcome`. **No ET gold rows generated in this PR** — only schema readiness.

## Files allowed

- `packages/eval/schema.py` — extend enums + invariants
- `packages/eval/tests/test_employment_schema.py` — new
- `docs/eval/decision-log.md` — add D-022 entry recording option 1
- `docs/eval/gold-schema.md` — append ET-specific section (constraints, examples)

## Files forbidden

- `apps/**` — other tracks
- `packages/eval/case_file_adapter.py` (read-only — leakage contract; SHA-65f territory)
- `packages/eval/issue_alignment.py` (read-only — housing-specific matter mapping)
- `packages/eval/adapter.py` (read-only — orchestrator/eval determination conversion; updated in SHA-65f)
- `packages/eval/compare.py`, `packages/eval/metrics/calibration.py` (read-only — downstream consumers; updated when ET gold rows actually exist)
- `data/gold_standard/**` — no ET rows generated here (SHA-148)
- `scripts/scrapers/**` — separate worktree (SHA-145, SHA-146)

## DoD (from SHA-144 ticket)

- [ ] `ClaimType` adds `UNFAIR_DISMISSAL`. Housing values unchanged.
- [ ] `PartyRole` adds `CLAIMANT`, `RESPONDENT_EMPLOYER`. Housing values unchanged.
- [ ] `Winner` adds `CLAIMANT`, `RESPONDENT`. Housing values + `SPLIT` unchanged.
- [ ] `Determination` adds forum-neutral `CLAIMANT_SUCCESS`, `RESPONDENT_SUCCESS`, `PARTIAL_SUCCESS`, `NON_MERITS`. Housing Ombudsman values unchanged.
- [ ] `_legacy_winner_for` extended to map the new determinations.
- [ ] `GroundTruthOutcome` gains optional remedy fields: `basic_award_gbp`, `compensatory_award_gbp`, `deductions_pct`, `uplifts_pct`, `reinstatement_sought`, `reinstatement_granted`, `re_engagement_sought`, `re_engagement_granted`. All `Optional[...]`, default `None`. Validator: these may only be set when `domain_id` is in the employment family.
- [ ] `GoldCase._validate_invariants`: INV-2 (party roles) branches on domain family. Housing requires tenant+landlord; employment requires claimant+respondent_employer.
- [ ] `GoldCase._validate_invariants`: `disputed_amount_gbp` / `claimed_amounts` exemption extended from a `housing.repairs_social.v1` literal to a list-driven check that also covers `employment.*` domains. Employment requires `ground_truth_outcome.determination` set (INV-D5).
- [ ] **Forum-coercion guard (INV-F1)**: a housing-family `domain_id` rejects employment enum values (CLAIMANT, RESPONDENT_EMPLOYER, UNFAIR_DISMISSAL, CLAIMANT_SUCCESS/RESPONDENT_SUCCESS/PARTIAL_SUCCESS/NON_MERITS), and an employment-family `domain_id` rejects housing enum values (TENANT, LANDLORD, AGENT, MALADMINISTRATION/etc, CLEANING/DAMAGES/etc).
- [ ] `packages/eval/tests/test_employment_schema.py` covers: valid ET gold case, housing case unchanged, cross-forum coercion rejected, missing determination on employment rejected, remedy fields gated on domain family, winner aggregation works with claimant/respondent.
- [ ] All existing `packages/eval/tests/` (727 tests) still pass — 0 regressions.
- [ ] `docs/eval/decision-log.md` records D-022 (option 1 chosen over option 2, with rationale).

## Out of scope (do not do here)

- Downstream consumer updates (compare.py, calibration.py, adapter.py, case_file_adapter.py) — they'll be updated when SHA-148 / SHA-65f land ET gold rows that actually exercise those paths.
- Live scraping (SHA-146) — SHA-145 worktree.
- Vector/BM25 ingestion (SHA-147).
- Gold-set generation (SHA-148).
- Factor catalog (SHA-149).

## Notes

- User chose option 1 (extend) over spec-recommended option 2 (adapter). Trade-off accepted: more validator complexity in one schema, but one canonical `GoldCase` for both housing and employment so retrieval/factor/metrics code stays single-source.
- The forum-coercion guard (INV-F1) is the *whole point* of the user's choice — without it, option 1 collapses into "enum sprawl with no guarantee of forum consistency". Tests must prove both directions of coercion are refused.
- Memory note: project venv at `/Users/msharif/Documents/Projects/proposer/legal-mediation-system/venv/`. Use `venv/bin/python -m pytest` from this worktree. Never `pip install --user`.
