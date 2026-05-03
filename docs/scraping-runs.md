# Scraping Runs — Operational Log

Chronological record of every live scraping pilot. One section per run with inputs, hit-rate findings, follow-ups filed, and the resulting corpus state. Read top-to-bottom to understand how the housing-domain corpora landed; jump to a specific section if you're debugging a specific scraper.

> **Why this exists**: scraper code lives in git, but the *operational story* (what hit rate did the live API actually give us, what bugs surfaced only against real HTML, why we pivoted from RRO to MNR) doesn't fit in a commit message and gets lost in Linear comments. This is the durable record.

---

## Index

| # | Date | Source | Linear | PR | Outcome |
|---|---|---|---|---|---|
| 1 | 2026-05-03 | Housing Ombudsman | [SHA-136](https://linear.app/sharifbuilders/issue/SHA-136) | [#25](https://github.com/MSH4R1F/proposer/pull/25) | 10 docs / 94 chunks ingested; pagination bug uncovered |
| 2 | 2026-05-03 | GOV.UK FTT(PC) RRO | [SHA-137](https://linear.app/sharifbuilders/issue/SHA-137) | [#25](https://github.com/MSH4R1F/proposer/pull/25) | 1 doc; corpus rarity ~0.1% — pivoted to MNR |
| 3 | 2026-05-03 | GOV.UK FTT(PC) MNR | [SHA-138](https://linear.app/sharifbuilders/issue/SHA-138) | [#26](https://github.com/MSH4R1F/proposer/pull/26) | 50 docs / 169 chunks; **100% rent extraction** |

---

## Run 1 — Housing Ombudsman (SHA-136)

### Goal
Run the merged SHA-125 scraper against the live Housing Ombudsman site and populate `housing.repairs_social.v1`.

### Command
```bash
python -m scripts.scrapers.housing_ombudsman.ombudsman_scraper \
  --max-keep 30 --max-listing-pages 20 -v
```

### Result

| Metric | Value |
|---|---|
| Cases seen | 10 |
| Cases kept | **10** |
| Cases excluded | 0 |
| Listing pages visited | 1 (out of 20 cap) |
| Robots respected | yes |
| Rate held | 1 rps |
| Total run time | ~24 s |

Matter-type breakdown (multi-tag): `complaint_handling_failure=8`, `repairs_disrepair=8`, `repairs_damp_mould=3`. Outcome label was `unknown` for all 10 — the heuristic doesn't yet detect Ombudsman determinations beyond a generic catch-all.

### Bug surfaced — pagination CSS selector mismatch

`find_next_listing_page()` returned `None` despite `--max-listing-pages 20`. The pager selector `li.pager__item--next a, a.pager__item--next, a[rel='next']` doesn't match the live `housing-ombudsman.org.uk` markup — likely JS-driven pagination or a Drupal markup change since the scraper was first written. Filed as a follow-up; the pilot capped at 10 docs in consequence.

### Bug surfaced — `embed_documents` typo in ingest

Re-running ingest crashed with `AttributeError: 'OpenAIEmbeddings' object has no attribute 'embed_documents'`. The actual method on `BaseEmbeddings` is `embed_texts`. Patched in `scripts/ingest/run_ombudsman_ingest.py` and (after CodeRabbit review) the matching test in `scripts/scrapers/housing_ombudsman/tests/test_smoke_retrieval.py`.

### Ingest

```bash
python scripts/ingest/run_ombudsman_ingest.py
```
- **10 docs → 94 chunks** (range 3–20 per doc, depending on length)
- Embedded via `text-embedding-3-small` in two batches (50 + 44, 21k + 19k tokens)
- Persisted to ChromaDB collection `housing_ombudsman_determinations_v1` under `data/indices/housing_repairs_social_v1/research_seed_2026_05/chroma/`
- BM25 sidecar at `…/bm25.pkl`
- Manifests in `…/manifests/`

### Smoke retrieval

Query: `"tenant complaint damp mould landlord disrepair"`. Top-3 cosine 0.66–0.69, all from real Ombudsman determinations (Lewisham, Greenwich, West Northamptonshire). All 94 chunks carry `domain_id=housing.repairs_social.v1`, `forum=housing_ombudsman`, `source_publisher=housing_ombudsman`, `source_license=unknown_housing_ombudsman_decisions_permission_pending`.

### Licence note

`data/raw/housing_ombudsman/SOURCE_RIGHTS.md` records that redistribution permission is pending — every emitted chunk's `source_license` is therefore the `unknown_..._permission_pending` sentinel until that's resolved. Internal-research use only.

---

## Run 2 — GOV.UK FTT(PC) Rent Repayment Orders (SHA-137)

### Goal
Run the merged SHA-126 scraper against the live GOV.UK Residential Property Tribunal listing and populate `housing.property_chamber.rro.v1`.

### Commands

Two runs were performed. First with the original 1 rps / 20 pages cap, then a longer 60 pages / 2 rps run to confirm rarity:

```bash
# Run 2a — first pilot
python -m scripts.scrapers.govuk_property_tribunal.govuk_scraper \
  --max-keep 30 --max-pages 20 --rps 1.0

# Run 2b — confirmation run on new pages
python -m scripts.scrapers.govuk_property_tribunal.govuk_scraper \
  --max-keep 30 --max-pages 60 --rps 2.0
```

### Result

| Metric | Run 2a | Run 2b |
|---|---|---|
| Pages visited | 20 | 60 (capped) |
| Total hits seen | 1 000 | ~3 000 |
| Cases kept (RRO) | **1** | 0 new |
| Cases excluded | 999 | ~3 000 |
| Hit rate | 0.10 % | 0 % |

The single accepted case — `MAN/00BY/HMG/2024/0602` — matched all eight statutory grounds in the filter allowlist (HA 2004 ss.30/32/95, PEA 1977 s.1(2), CLA 1977 s.6, HPA 2016 s.21/ss.40-52, Renters' Rights Act 2025 s.16J).

### Key finding — RROs are corpus-rare

The GOV.UK `/api/search.json` endpoint returns 16 597 total Residential Property Tribunal decisions; matter-code breakdown of the rejected set:

| Code | Count | Meaning |
|---|---|---|
| MNR | 136 | s.13 rent-increase referral |
| LDC | 126 | s.20 dispensation from consultation |
| LSC | 100 | service-charge dispute |
| HMF | 35 | HMO licence / fee |
| HNA | 19 | improvement-notice appeal |
| (long tail) | ~250 | leasehold, Park Homes, fair rents, etc. |

Almost everything in this corpus is leasehold or service charge; RRO under HPA 2016 ss.40-52 is rare because the FTT(PC) doesn't tag a distinct "RRO" matter-code (the case carries the *underlying-offence* code like HMG/HMF/HNA). I probed `filter_tribunal_decision_sub_category=housing-act-2004-and-housing-and-planning-act-2016---rent-repayment-orders` — the GOV.UK search API accepts it but returns hits whose `tribunal_decision_sub_category` field is `None`, so the filter is non-functional server-side. There is no source-side narrowing path.

### Decision: pivot to MNR

`≥15 kept RRO docs` was not achievable from this single source. Rather than chase MNR-adjacent sources (Upper Tribunal Lands Chamber appeals, BAILII), we pivoted scope to **MNR rent-determination** — same publisher, same tribunal, ~9 % of the corpus, same engineering substrate, much better mediation fit. See [Run 3](#run-3--govuk-fttpc-mnr-rent-determination-sha-138).

### Ingest (the 1 doc that did land)

```bash
python scripts/ingest/run_govuk_pc_rro_ingest.py --max-docs 30
```
- **1 doc → 11 chunks** in `housing_property_chamber_rro_v1` ChromaDB collection
- Pipeline proven end-to-end (search → content API → PDF → parser → filter → ingest)
- Cross-namespace isolation against the Ombudsman corpus verified

### Licence note

GOV.UK Crown copyright under OGL-3.0 — `source_license=OGL-3.0` on every emitted chunk. Permissive use.

---

## Run 3 — GOV.UK FTT(PC) MNR rent-determination (SHA-138)

### Goal
After the SHA-137 RRO pivot, build a new scraper for MNR — section 13 rent-increase referrals decided under Housing Act 1988 s.14. Numeric outcome (£/period), tenant-vs-landlord money dispute, abundant in the corpus, ideal mediation fit.

### Command

```bash
python -m scripts.scrapers.govuk_rent_determination.govuk_scraper \
  --max-keep 50 --max-pages 8 --rps 2.0
```

### Result

| Metric | Value |
|---|---|
| Pages visited | 3 (out of 8 cap) |
| Total hits seen | 150 |
| Cases kept | **50** (hit `--max-keep` cap) |
| Hit rate | **33 %** |
| Robots respected | yes |
| Rate held | 2 rps |

**330× denser than RRO** — that is the entire reason for the pivot landing on MNR.

### Bug surfaced — content-API stub vs. PDF

First pass extracted zero rent fields. The cause: `/api/content/<base_path>` returns a *stub* body for FTT(PC) decisions — the literal text `"Read the full decision in <REF>"`. The actual decision text is always in the PDF attachment. The first-pass scraper only fell back to PDF when the body was empty; the stub satisfied the empty-check.

Fixed in the same branch: any body shorter than 200 chars now triggers PDF extraction.

### Re-extraction across the pilot

After the fix, I re-ran the rent extractor over the 50 already-downloaded PDFs (no fresh scraping required):

| Field | Hit rate |
|---|---|
| `decided_rent_amount` | **50/50 = 100 %** |
| `decided_rent_period` | 50/50 (PCM=47, PW=1, PQ=1, fortnight=1) |
| `landlord_proposed_rent_amount` (s.13 notice) | 30/50 = 60 % |
| `existing_rent_amount` | 29/50 = 58 % |
| `statute_basis` (HA 1988 s.13/s.14) | 50/50 = 100 % (s.13 = 23, s.14 = 27) |

That's a clean, calibration-ready outcome dataset: every decision has a numeric outcome, most have the landlord's ask and the tenant's pre-notice rent for ZOPA bracket calculation, all are anchored to the statutory provision the tribunal applied.

### Ingest

```bash
python scripts/ingest/run_govuk_mnr_ingest.py --max-docs 50
```
- **50 docs → 169 chunks** in `housing_rent_determination_v1` ChromaDB collection
- BM25 + corpus + run manifests written under `data/indices/housing_rent_determination_v1/research_seed_2026_05/`
- Smoke retrieval: top-3 cosine 0.68–0.69 for `"section 13 rent increase notice landlord proposed market rent"` — all hits real s.13 decisions
- Cross-namespace isolation verified: `domain_id=housing.rent_determination.v1`, distinct collection (`rent_determination_v1`), distinct persist dir, distinct `matter_types=rent_determination` stamp on every chunk

### Licence note

OGL-3.0. Permissive.

---

## Cross-cutting observations

### Politeness / robots
All three scrapers respect `robots.txt` by default and self-throttle to ≤2 rps. No CAPTCHAs or 429s observed in any run. User-Agent is `ProposerResearchBot/0.1 (+https://github.com/MSH4R1F/proposer; ...)`.

### Idempotency / resume
Every scraper writes a `master_index.json` plus an append-only `_runs/<run_id>.jsonl`. A killed run resumes by content-hash dedup on the next invocation. The MNR scraper, the RRO scraper, and the Ombudsman scraper all share this contract via `progress.py`.

### What CodeRabbit caught (PR #26)

A bm25_index_path mismatch between the new YAML and the ingest's actual write-path (now corrected to `data/indices/housing_rent_determination_v1/research_seed_2026_05/bm25.pkl`); the same `embed_documents` typo lurking in the Ombudsman smoke-retrieval test (now patched); a "Tenant v Landlord" party-assignment inversion (replaced with an entity-suffix heuristic — `Ltd / Council / Properties / Housing / Trust` etc.); a deprecated `datetime.utcnow()`; a stale `SHA-126: RRO scraper` docstring in the MNR downloader; a silent skip in `MasterIndex.load()` that now logs at DEBUG.

### Corpus state at end of pilots (2026-05-03)

| Namespace | Source | Docs | Chunks | Status |
|---|---|---|---|---|
| `housing_repairs_social_v1` | Housing Ombudsman | 10 | 94 | pilot |
| `housing_property_chamber_rro_v1` | GOV.UK FTT(PC) RRO | 1 | 11 | pilot (corpus-bounded) |
| `housing_rent_determination_v1` | GOV.UK FTT(PC) MNR | 50 | 169 | **pilot complete** |

---

## How to reproduce / re-run

```bash
# 1. Activate the shared venv at the repo root
source venv/bin/activate

# 2. Source secrets (OPENAI_API_KEY for ingest)
set -a && source .env && set +a

# 3. Scrape (pick one; --output-dir / --max-keep are tunable)
python -m scripts.scrapers.housing_ombudsman.ombudsman_scraper --max-keep 30 -v
python -m scripts.scrapers.govuk_property_tribunal.govuk_scraper --max-keep 30 --rps 1.0
python -m scripts.scrapers.govuk_rent_determination.govuk_scraper --max-keep 50 --rps 2.0

# 4. Ingest into the matching namespace
python scripts/ingest/run_ombudsman_ingest.py
python scripts/ingest/run_govuk_pc_rro_ingest.py --max-docs 30
python scripts/ingest/run_govuk_mnr_ingest.py --max-docs 50

# 5. Smoke-check retrieval (PYTHONPATH=packages required for direct imports)
PYTHONPATH=packages python -c "
from pathlib import Path
from rag_engine.config import RAGConfig
from rag_engine.vectorstore.chroma_store import ChromaStore
cfg = RAGConfig(
    chroma_persist_dir=Path('data/indices/housing_rent_determination_v1/research_seed_2026_05/chroma'),
    collection_name='rent_determination_v1',
)
print('chunks:', ChromaStore(cfg)._collection.count())
"
```

For follow-up tickets (Ombudsman pagination fix, broader RRO sourcing, MNR corpus expansion to ≥200 docs, LSC/F77 second slices), see Linear sub-tickets under [SHA-64](https://linear.app/sharifbuilders/issue/SHA-64).
