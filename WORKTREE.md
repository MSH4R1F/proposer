# WORKTREE — SHA-145 / SHA-65a: Employment Tribunal scraper code

**Linear**: [SHA-145](https://linear.app/sharifbuilders/issue/SHA-145) (logical name SHA-65a; child of [SHA-65](https://linear.app/sharifbuilders/issue/SHA-65)).
**Branch**: `feature/sha-145-sha-65a-employment-tribunal-scraper-code`
**Created**: 2026-05-13 off `main@be8cb3a8`.
**Design spec**: [`docs/superpowers/specs/2026-05-13-employment-tribunal-vertical-design.md`](../../docs/superpowers/specs/2026-05-13-employment-tribunal-vertical-design.md)
**Sibling tickets**: SHA-144 (schema gate) · SHA-146 (pilot) · SHA-147 (full scrape) · SHA-148 (gold) · SHA-149 (factor catalog) · SHA-150 (evals)

## What this worktree owns

Build the GOV.UK Employment Tribunal scraper module at `scripts/scrapers/employment_tribunal/`, mirroring `scripts/scrapers/housing_ombudsman/`. **No live scrape** — that lives in SHA-146.

## Files allowed

- `scripts/scrapers/employment_tribunal/**` (new package)
- `scripts/scrapers/employment_tribunal/tests/**` (new tests + fixture HTML samples)
- `data/raw/employment/SOURCE_RIGHTS.md` (OGL v3.0 attribution — committed; matches the project gitignore allowlist at `data/raw/**/SOURCE_RIGHTS.md`)

## Files forbidden

- `apps/**` — other tracks
- `packages/**` — read-only for this worktree (the existing PII redactor / SourceDocument are imported, not modified)
- `scripts/scrapers/housing_ombudsman/**` (read-only — reference pattern)
- `scripts/scrapers/govuk_property_tribunal/**` (read-only — reference pattern)
- `data/gold_standard/**` — gold-set work belongs to SHA-148
- `packages/eval/schema.py` — schema changes belong to SHA-144

## DoD (from SHA-145 ticket)

- [ ] Module layout matches: `__init__.py`, `config.py`, `models.py`, `downloader.py`, `filter.py`, `parsers.py`, `progress.py`, `to_source_document.py`, `govuk_scraper.py`, `tests/`.
- [ ] Two-stage filter: Stage 1 GOV.UK category, Stage 2 merits-quality with reason codes for preliminary/strike-out/withdrawal/default/remedy-only/non-lead exclusions.
- [ ] Persisted record carries: public page URL, GOV.UK base path, case title, case number(s), decision date, country, jurisdiction labels, attachment metadata, source hash, observed licence (default OGL-3.0 only where supported), parser version.
- [ ] OGL v3.0 attribution string in `models.py` AND `data/raw/employment/LICENCE.md`.
- [ ] PII redactor wired in `to_source_document.py` (postcode, phone, email, NI number, claimant names) — model-facing only.
- [ ] Unit tests pass against fixture HTML — no network.
- [ ] CLI runs with `--dry-run --max-keep N` without hitting the network.
- [ ] PR description includes a copy of the OGL-3.0 attribution string.

## Out of scope (do not do here)

- Live scraping (SHA-146).
- Vector/BM25 ingestion (SHA-147).
- Gold-set generation (SHA-148, gated on SHA-144).
- Factor catalog (SHA-149).
- Schema changes to `GoldCase` (SHA-144).
