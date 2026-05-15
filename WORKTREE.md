# WORKTREE — SHA-147 / SHA-65c: 1000-doc ET unfair-dismissal corpus

**Linear**: [SHA-147](https://linear.app/sharifbuilders/issue/SHA-147) (logical name SHA-65c; child of [SHA-65](https://linear.app/sharifbuilders/issue/SHA-65)).
**Branch**: `feature/sha-147-sha-65c-1000-doc-et-unfair-dismissal-corpus-namespace-ingest`
**Created**: 2026-05-15, branched off `feature/sha-145-sha-65a-employment-tribunal-scraper-code@fb35f065` (post-pilot fixes).
**Design spec**: [`docs/superpowers/specs/2026-05-13-employment-tribunal-vertical-design.md`](../../docs/superpowers/specs/2026-05-13-employment-tribunal-vertical-design.md) §3, §4 (SHA-65c row)
**Predecessors**: SHA-145 ✅ scraper + fixes (in parent branch) · SHA-146 ✅ 30-doc pilot

## What this worktree owns

Run the SHA-145 scraper (post-SHA-146-fixes) to capture ~1000 kept unfair-dismissal decisions. Persist the corpus manifest + excluded manifest + run report so SHA-148 (gold) and SHA-65f (evals) have a frozen reference corpus.

**Year window pivot (2026-05-15):** the original spec specified 2019-2024 for thesis reproducibility. The SHA-146 pilot proved that **GOV.UK's ET listing page does not honour any documented date filter param** — 6 variants tested (`decision_date_from[year]`, `decision_date_from`, `public_timestamp[from]`, etc) all returned the same 2025-2026 latest decisions. The listing simply doesn't paginate back through history. Pivot: run with `--years 2019-2026` so the in-code post-filter never rejects valid 2025-2026 data. SHA-148 will do its own train/test split based on actual decision dates.

**Rate:** 2.0 rps (per user). ~1500-1700 cases seen at ~60% accept rate → estimated 15-17 min runtime.

## Files allowed

- `data/eval_artifacts/corpus/employment_et_unfair_dismissal_v1_<date>.jsonl` (kept manifest)
- `data/eval_artifacts/corpus/employment_et_unfair_dismissal_v1_<date>_excluded.jsonl` (rejected manifest)
- `data/eval_artifacts/corpus/employment_et_unfair_dismissal_v1_<date>_report.md` (run report)
- Working artifacts under `data/raw/employment/` are gitignored per `.gitignore:279`.

## Files forbidden

- `scripts/scrapers/employment_tribunal/**` — code in SHA-145 branch
- `packages/eval/schema.py` — schema in SHA-144 branch
- `apps/**` — other tracks

## DoD (from SHA-147 ticket, pragmatic v1)

Original ticket includes BM25 + Chroma ingestion + cross-domain leakage assertions. Those depend on external services (OpenAI embeddings for vector collection) and run on different machines. This PR delivers the **scrape + manifests + report**; ingestion belongs in a SHA-147-followup PR once the embedding pipeline is wired and the eval harness owner signs off.

- [ ] 1000-ish kept rows captured at `--rps 2.0` (gate: ≥800 kept)
- [ ] Stage-2 filter reasons honest (strike-out / reconsideration / not-lead / out-of-window distributed across rejects, none silent)
- [ ] No PII leakage in committed manifests (regression sweep)
- [ ] Corpus stats in report: count by decision year, count by country, count by Stage-2 exclusion reason
- [ ] Frozen corpus version string recorded: `corpus_version=research_seed_2026_05` (matches the YAML)
- [ ] **Deferred** to follow-up: vector/BM25 ingestion + cross-domain leakage assertion (requires OPENAI_API_KEY + chroma setup)

## Notes

- Project venv at `legal-mediation-system/venv/`. Use `venv/bin/python -m scripts.scrapers.employment_tribunal.govuk_scraper …`.
- When the SHA-145 PR merges, this branch rebases against main.
- PII redaction code path runs on every doc; live GOV.UK already pre-redacts most claimant identifiers upstream so observed counters will be near-zero (same as SHA-146 pilot found). Synthetic-PII regression tests in [`test_to_source_document.py`](../../scripts/scrapers/employment_tribunal/tests/test_to_source_document.py) carry the proof the redactor actually fires.
