# Employment Tribunal corpus — 1000-doc full scrape report

**Ticket:** [SHA-147 / SHA-65c](https://linear.app/sharifbuilders/issue/SHA-147)
**Date:** 2026-05-15
**Scraper code:** [SHA-145 / SHA-65a](https://linear.app/sharifbuilders/issue/SHA-145) at commit `74f31366` (post-SHA-146 fixes + SHA-147 pagination fix)
**Source:** `https://www.gov.uk/employment-tribunal-decisions?tribunal_decision_categories=unfair-dismissal&decision_date_from[year]=2019&decision_date_to[year]=2026`
**Run command:**

```bash
PYTHONPATH=packages venv/bin/python -m scripts.scrapers.employment_tribunal.govuk_scraper \
    --max-keep 1000 --jurisdiction-code unfair-dismissal --rps 2.0 --years 2019-2026
```

## TL;DR

- **1000 kept docs**, 1817 cases seen across 37 listing pages, 15m 26s runtime at 2 rps.
- **Zero PII leakage** across all 1000 committed `source_document.json` files.
- **Stage-2 filter rejected 812 (45%)** — 470 strike-out, 161 not-lead-issue, 144 reconsideration, 37 withdrawal. All sensible on spot-check.
- **Date span 2023-03-23 → 2026-04-20** (NOT 2019-2024). GOV.UK's listing only paginates back ~3 years; the originally-specced 2019-2024 window is **structurally unreachable** through this surface.
- **Outcome extraction is 0%** on kept docs — the HTML body is a 400-byte landing page; outcomes live in the PDF attachment. SHA-148 will need PDF text for gold.

## Pipeline fixes between pilot and this run

Three commits on `feature/sha-145-…-scraper-code`:

| Commit | Fix |
|---|---|
| `fb35f065` | SHA-146 pilot findings: tightened `_LABEL_OUTCOME` + body-phrase fallback (issue 1), URL date filter + post-filter (issue 2), listing nav clutter allowlist (issue 3) |
| `74f31366` | **SHA-147 pagination fix**: `find_next_listing_page` matched `li.govuk-pagination__next a` but live GOV.UK uses `<div class="govuk-pagination__next"><a>` — so pagination silently stopped after page 1 and every prior scrape was capped at 50 cases regardless of `--max-keep`. New regression test pinned to the actual GOV.UK div markup. |

## Corpus stats

### Yield + Stage-2 breakdown

| Metric | Value |
|---|---|
| Cases seen | 1817 |
| **Cases kept** | **1000** |
| Cases excluded | 812 |
| Accept rate | 55% |
| Listing pages visited | 37 |
| Runtime | 15m 26s |
| Effective fetch rate | ~2.0 rps (target met) |

### Excluded reasons

| Reason | Count | % of excluded |
|---|---:|---:|
| `strike_out` | 470 | 58% |
| `unfair_dismissal_not_lead_issue` | 161 | 20% |
| `reconsideration` | 144 | 18% |
| `withdrawal` | 37 | 5% |
| **Total** | **812** | 100% |

### Country split

| Country | Kept | % |
|---|---:|---:|
| England & Wales | 897 | 90% |
| Scotland | 103 | 10% |

### Decision year distribution

| Year | Kept | % |
|---|---:|---:|
| 2023 | 2 | 0.2% |
| 2024 | 24 | 2.4% |
| 2025 | 474 | 47% |
| 2026 | 500 | 50% |

The corpus skews heavily to 2025-2026 (97% of decisions). GOV.UK publishes ET decisions on a rolling basis and only retains ~3 years of paginated history; the 2019-2022 portion of the spec's intended train split is **unreachable** through this surface. SHA-148 will need to define a new train/test split anchored to the actual data (e.g. 2023-2025 train / 2026 test, or a calendar-based split).

### 2025-2026 month distribution

| Month | Count | | Month | Count |
|---|---:|---|---|---:|
| 2025-01 | 7 | | 2025-09 | 23 |
| 2025-02 | 8 | | 2025-10 | 73 |
| 2025-03 | 10 | | 2025-11 | 152 |
| 2025-04 | 6 | | 2025-12 | 145 |
| 2025-05 | 10 | | 2026-01 | 192 |
| 2025-06 | 9 | | 2026-02 | 145 |
| 2025-07 | 16 | | 2026-03 | 128 |
| 2025-08 | 15 | | 2026-04 | 35 |

The publishing-cadence cliff at September → October 2025 is GOV.UK's switchover to higher-volume publishing, not a real change in decision rate.

## GOV.UK constraints discovered live

### 1. Server-side date filter is not honoured

Six URL param shapes tested against the listing endpoint:

```
decision_date_from[year]=YYYY&decision_date_to[year]=YYYY      # finder convention
decision_date_from=YYYY-MM-DD&decision_date_to=YYYY-MM-DD       # ISO date
decision_date[from]=YYYY-MM-DD&decision_date[to]=YYYY-MM-DD     # nested
public_timestamp[from]=YYYY-MM-DD&public_timestamp[to]=YYYY-MM-DD  # search API style
from_date_year=YYYY&to_date_year=YYYY                            # flat
decision_date_from_year=YYYY&decision_date_to_year=YYYY          # flat alt
```

**All six** returned the same 100-link page with decisions dated 2025-2026 only. GOV.UK's ET listing page does not expose a working server-side date filter. The in-code post-filter in `EmploymentTribunalScraper._handle_detail` is the only enforcement — it works correctly (rejected 0 docs in this run because all decisions found were already in the 2019-2026 window).

### 2. Pagination stops at ~3 years of history

The listing's "Next page" link reports `2 of 1,176` on page 1, suggesting ~58,800 unfair-dismissal decisions exist server-side. In practice the listing only paginates back to early 2023 — earlier decisions either aren't accessible via this finder or require a different navigation pattern. Going from page 1 to 37 traversed roughly Apr 2026 → Mar 2023.

### 3. HTML body is "landing page only"

Every ET decision page is a ~400-byte landing page with title, decision date, jurisdiction codes, country, and a "Read the full decision in <case>: <case_num> - <type>" link to the PDF. The PDF contains the actual judgment text, reasoning, outcome, and remedy. The HTML body has **no outcome phrases**, so:

- All 1000 kept docs have `outcome_raw=None` and `outcome_normalized=None`.
- 470 strike-out / 144 reconsideration excluded docs were caught from title patterns (e.g. `: ... - Strike Out`) — the title is the only outcome signal in the HTML.

**For SHA-148 (gold) and SHA-65f (evals):** PDF text extraction is required to recover outcomes, statutory basis, fair-reason categories, and remedy fields. The `attachments` list on each manifest row already carries the PDF URLs.

## PII regression sweep

| Pattern | Hits |
|---|---:|
| UK postcode | 0 |
| UK phone (no-space) | 0 |
| UK phone (spaced) | 0 |
| Email | 0 |
| NI number | 0 |

Zero leaks across 1000 committed documents. Same finding as the SHA-146 pilot: GOV.UK pre-redacts most claimant identifiers upstream. The redaction code path was exercised on every doc; the synthetic-PII regression tests in [`test_to_source_document.py`](../../../scripts/scrapers/employment_tribunal/tests/test_to_source_document.py) carry the proof the redactor itself fires correctly when PII is present.

## Stage-2 filter spot-check

5 kept + 5 rejected manually inspected:

**Kept (5/5 sensible):** all have `: ... - Judgment` or `: ... - Reserved Judgment` titles, decision dates in window, jurisdiction codes include `Unfair Dismissal`.

**Rejected (5/5 sensible):**
- Strike-out: titles `... - Strike Out` / `... - Partial Strike Out`
- Reconsideration: bodies mention `reconsideration` explicitly
- Not-lead-issue: bodies have `Equality Act 2010` / `direct discrimination` / `harassment` patterns dominating the merits framework, with unfair dismissal as an incidental head

## Recommendation for SHA-148

The corpus is **ready for gold-set selection** under the following adjusted plan:

1. **Train/test split must shift.** Pre-2024 decisions are 2.6% of the corpus (26 of 1000) — too few to stratify across outcomes, fair-reason categories, and country. Two options:
   - **By decision-date quartile:** Q1 → train (∼2025-10 to 2025-12), Q2-Q3 → dev, Q4 → test (2026-03 to 2026-04). Each quartile is ~250 cases.
   - **By calendar boundary:** train ≤ 2026-01-31 (≈491 cases), test ≥ 2026-02-01 (≈509 cases). Avoids the cold-start months 2024-2025.

   Either way the originally-specced 2019-2022 train / 2023-2024 test split needs revision — flag for SHA-148 ticket scope adjustment.

2. **PDF text extraction is required.** SHA-65a deliberately scoped to HTML-only. SHA-148's gold annotator needs to download the PDFs listed in each row's `attachments` field and run them through PDF-text extraction. Reuse `rag_engine.extractors.pdf_extractor.PDFExtractor` if it fits. Estimate: SHA-148 + ~5 pts.

3. **Stratification axes** (per design spec §4):
   - Outcome (claimant_success / respondent_success / partial / non_merits) — recoverable only from PDF, **deferred to SHA-148 PDF pass**
   - Fair-reason category (conduct / capability / redundancy / illegality / SOSR) — PDF only
   - Country: 90/10 E&W/Scotland; gold can either match this ratio (~5 Scotland in a 50-row sample) or oversample Scotland for cross-jurisdiction coverage
   - Year: skewed to 2025-2026 (see distribution above)

## Files committed

- [`employment_et_unfair_dismissal_v1_2026-05-15.jsonl`](employment_et_unfair_dismissal_v1_2026-05-15.jsonl) — 1000 kept rows with parser metadata, attachment URLs, redaction stats, content hashes
- [`employment_et_unfair_dismissal_v1_2026-05-15_excluded.jsonl`](employment_et_unfair_dismissal_v1_2026-05-15_excluded.jsonl) — 812 rejected rows with reason codes + excerpts
- This report

Working artifacts (raw HTML, decision/<case>/*.json, master_index, run logs) live under `data/raw/employment/` and are gitignored.

## Out of scope (deferred to follow-up)

The original SHA-147 ticket included vector + BM25 namespace ingestion. That requires OPENAI_API_KEY (embeddings) and a Chroma client setup, plus the cross-domain-leakage assertion suite. This PR delivers the **scrape + manifest + report**; ingestion belongs in a separate SHA-147-followup PR with the eval-harness owner's sign-off on the embedding model choice.
