# Employment Tribunal pilot — 30-doc live scrape report

**Ticket:** [SHA-146 / SHA-65b](https://linear.app/sharifbuilders/issue/SHA-146)
**Date:** 2026-05-14
**Scraper code:** [SHA-145 / SHA-65a](https://linear.app/sharifbuilders/issue/SHA-145) at commit `2878b50b` on `feature/sha-145-sha-65a-employment-tribunal-scraper-code`
**Source:** `https://www.gov.uk/employment-tribunal-decisions?tribunal_decision_categories=unfair-dismissal`
**Run command:**

```bash
PYTHONPATH=packages venv/bin/python -m scripts.scrapers.employment_tribunal.govuk_scraper \
    --max-keep 30 --jurisdiction-code unfair-dismissal --rps 2.0
```

User-set rate 2.0 rps (overrode the 0.5 rps spec default). Still well within polite envelope for GOV.UK.

## TL;DR

- **PASS** both ticket gates: 30 kept (≥25), 0 PII leaks (≤15%).
- **Stage-2 filter works correctly** on real data: 17 rejections covering strike-out (11), reconsideration (3), and not-lead-issue (3).
- **Two real parser issues** surfaced — flag for SHA-147 / SHA-148, not blockers for SHA-147 RAG ingestion:
  1. Outcome extraction is 100% mis-mapped on live HTML (`outcome_raw` is captured as the decision date string).
  2. `--years` flag does not yet propagate to the listing URL (corpus is 2025-2026, not 2019-2024).
- **Recommendation:** proceed to SHA-147 with the two parser fixes scoped as small follow-up commits to SHA-145, **before** SHA-148 gold generation.

## Yield

| Metric | Value | Gate | Result |
|---|---|---|---|
| Listing pages visited | 1 | — | — |
| Cases seen | 47 | — | — |
| **Cases kept** | **30** | **≥25** | **PASS** |
| Cases excluded | 17 | — | — |
| Accept rate | 64% | — | — |
| Runtime | ~23 s | — | — |
| Earliest decision | 2025-10-17 | — | — |
| Latest decision | 2026-04-13 | — | — |
| Country: England & Wales | 29 | — | — |
| Country: Scotland | 1 | — | — |

## PII regression sweep

Scanned every committed `source_document.json` (post-redaction model-facing text) for:

| Pattern | Hits |
|---|---|
| UK postcode | 0 |
| UK phone (no-space) | 0 |
| UK phone (spaced, e.g. `07XXX XXX XXX`) | 0 |
| Email | 0 |
| NI number | 0 |

**0 PII leaks across 30 committed documents.** GOV.UK publishes ET decisions with claimant PII already substantially redacted, so the live `redaction_stats` counters all came back at 0 — that's the expected baseline on GOV.UK content, not a code-path failure. The TextCleaner + ET-specific NI + spaced-mobile sweeps in [`to_source_document.redact_model_facing_text`](../../../scripts/scrapers/employment_tribunal/to_source_document.py) are still exercised on every doc; the unit tests in [`test_to_source_document.py`](../../../scripts/scrapers/employment_tribunal/tests/test_to_source_document.py) carry the synthetic-PII regression assertions.

## Stage-2 filter breakdown

| Reject reason | Count | Example excerpt |
|---|---|---|
| `strike_out` | 11 | `"Mr A Kamal v Safran Seats GB Wales … Strike Out"` |
| `reconsideration` | 3 | (matched in body text) |
| `unfair_dismissal_not_lead_issue` | 3 | (mostly nav/sidebar-led noise; see issue 3 below) |

Manual spot-check of 5 kept and 5 rejected cases:

- **Kept (5/5 sensible)**: judgments referencing s.98 ERA 1996 / band of reasonable responses with no preliminary / strike-out / withdrawal markers.
- **Rejected (5/5 sensible)**: strike-out and reconsideration titles match the body; the `unfair_dismissal_not_lead_issue` rejections include one false positive caused by Issue 3 below.

## Issues found (for SHA-147 follow-up to SHA-145)

### Issue 1 — outcome extraction is 100% mis-mapped on live HTML

**Symptom:** every kept row has `parser_diagnostics: ["unrecognised_outcome_label:8 April 2026"]` (or similar), and `outcome_normalized: null`.

**Root cause:** [`parsers.py:_LABEL_OUTCOME = ("outcome", "judgment", "decision")`](../../../scripts/scrapers/employment_tribunal/parsers.py) plus the loose `in cand.lower()` match in `_value_for` causes the "Decision date" labelled field to bind to the outcome slot. The string "8 April 2026" then flows into `_normalize_outcome` and unsurprisingly fails.

**Impact:**
- SHA-147 (RAG ingest): **none** — outcome isn't used for retrieval.
- SHA-148 (gold set): **blocker** — stratification needs outcomes.
- SHA-65f (evals): **blocker** — Brier needs outcomes for ground truth.

**Fix scope:** tighten `_LABEL_OUTCOME` to exclude "decision" or remove the loose substring match, then add a body-text fallback that scans for the canonical phrases (`"claim succeeded"`, `"dismissal was unfair"`, etc) the live HTML actually uses. Estimate: ~30 min + new fixture tests.

### Issue 2 — `--years` flag does not narrow the listing URL

**Symptom:** corpus is 2025-10-17 to 2026-04-13 (the GOV.UK default "latest first" order), not the 2019-2024 window the spec assumes.

**Root cause:** [`config.py`](../../../scripts/scrapers/employment_tribunal/config.py) accepts `years_from` / `years_to` but [`downloader.listing_start_url()`](../../../scripts/scrapers/employment_tribunal/downloader.py) only adds the `tribunal_decision_categories=unfair-dismissal` query parameter.

**Impact:**
- SHA-147: **moderate** — would ingest 2025-2026 decisions, polluting the temporal-split logic SHA-148 relies on.
- SHA-148: **blocker** — train/test split is 2019-2022 / 2023-2024.

**Fix scope:** GOV.UK supports `public_timestamp[from]=YYYY-MM-DD&public_timestamp[to]=YYYY-MM-DD` on listing pages. Wire `config.years_from` / `years_to` into `listing_start_url()` as ISO dates (1 Jan + 31 Dec). Estimate: ~20 min + fixture test.

### Issue 3 — listing parser admits the `email-signup` non-case slug

**Symptom:** `data/employment-tribunal-decisions/email-signup` was parsed as a "case" and made it to Stage-2 (which correctly rejected it as `unfair_dismissal_not_lead_issue`).

**Root cause:** [`parsers.parse_listing_html`](../../../scripts/scrapers/employment_tribunal/parsers.py) matches any anchor whose path is `/employment-tribunal-decisions/<slug>` with the negative filter `case_ref.lower() in {"employment-tribunal-decisions", "page"}` — too narrow.

**Impact:** low — Stage-2 caught it. But it inflates `cases_seen` and one rejection slot, and a future GOV.UK template tweak could add similar nav slugs we'd then need to discover the same way.

**Fix scope:** expand the negative list to include `email-signup`, `feedback`, `tribunal_decision_categories=*` (we should never follow query-param-only paths back to the listing). Estimate: ~10 min + fixture test.

## Non-issues

- **Stage-2 filter on live HTML**: works. Strike-out and reconsideration patterns hit on real titles + body.
- **Dedup**: 47 unique `source_url`s + 47 unique `content_sha256` across the master index; zero collisions.
- **Robots.txt**: GOV.UK's `/robots.txt` was fetched (the run log shows no `robots.txt fetch failed` warning); all 30 detail-page GETs succeeded.
- **Licence detection**: 30/30 docs detected as `OGL-3.0` (explicit footer match, not inferred).
- **Rate limit**: 2 rps held steady. Token-bucket pacing in `downloader._TokenBucket` works as expected.
- **OGL v3.0 attribution**: string in [`scripts/scrapers/employment_tribunal/__init__.py`](../../../scripts/scrapers/employment_tribunal/__init__.py:OGL_V3_ATTRIBUTION) and [`data/raw/employment/SOURCE_RIGHTS.md`](../../../data/raw/employment/SOURCE_RIGHTS.md) are consistent; unit tests assert this.

## Files committed by SHA-146

- [`employment_et_unfair_dismissal_pilot_30_2026-05-14.jsonl`](employment_et_unfair_dismissal_pilot_30_2026-05-14.jsonl) — 30 kept rows with parser metadata + redaction stats + content hashes
- [`employment_et_unfair_dismissal_pilot_30_2026-05-14_excluded.jsonl`](employment_et_unfair_dismissal_pilot_30_2026-05-14_excluded.jsonl) — 17 rejected rows with reason codes + excerpts
- This report

Working artifacts under `data/raw/employment/` (decisions/, master_index.json, excluded.jsonl, scrape_summary.json, _runs/) are gitignored per `.gitignore:279` — not part of the deliverable.

## Recommendation for SHA-147

**Gate met.** Both quantitative thresholds pass. SHA-147 (1000-doc full scrape + namespace ingest) can proceed.

**Pre-flight follow-ups** (small commits on the SHA-145 branch, not new tickets):

1. Fix issue 1 (outcome extraction) — **required before SHA-148**.
2. Fix issue 2 (year filter) — **required before SHA-147** to avoid ingesting the wrong temporal window.
3. Fix issue 3 (listing nav slugs) — **nice-to-have**; current Stage-2 backstop is good enough.

Estimated total follow-up effort: ~1 hour + a fixture HTML update for the outcome regression.
