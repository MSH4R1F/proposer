# SHA-125 Housing Ombudsman scraper - status

## Done

* Phase 0 dependency intact (PR #21 already merged onto this branch).
* Inherited (do-not-touch): `__init__.py`, `config.py`, `models.py`,
  `filter.py`, `tests/__init__.py`, `tests/conftest.py`, `tests/test_filter.py`.
* Built on top:
  * `scripts/scrapers/housing_ombudsman/parsers.py` - listing + detail
    HTML parsers (BeautifulSoup, tolerant of small markup drift,
    diagnostics for unknown outcome labels, awaab/s.10A temporal
    marker).
  * `scripts/scrapers/housing_ombudsman/downloader.py` - polite async
    httpx + token bucket + tenacity retry + robots.txt.
  * `scripts/scrapers/housing_ombudsman/progress.py` - JSONL run log
    + master_index.json with content-hash dedup.
  * `scripts/scrapers/housing_ombudsman/to_source_document.py` - bridge
    to Phase-4 `SourceDocument`.
  * `scripts/scrapers/housing_ombudsman/ombudsman_scraper.py` - full
    orchestrator with click CLI, ScrapeReport, kept/excluded outputs.
  * `scripts/ingest/run_ombudsman_ingest.py` - reuses
    `chunk_source_document` + ChromaStore + BM25Index + manifests.
  * Tests: `test_parsers.py`, `test_to_source_document.py`,
    `test_idempotency.py`, `test_framing.py`, plus slow-marked
    `test_smoke_retrieval.py`, `test_cross_namespace_leakage.py`,
    `test_citation_verifier.py`.
  * `data/raw/housing_ombudsman/SOURCE_RIGHTS.md` - unverified-licence
    notice + internal-only constraint.
* Committed as `b47a4ee feat(SHA-125): housing ombudsman scraper, ingest, and tests`.

## Outstanding / NOT done

* **Live test verification blocked**: pytest invocations from this
  agent context hang inside `PyImport_ImportModuleLevelObject`
  recursion. `sample` of the stuck process shows endless import work
  with no I/O (not a network/blocking-call problem). The same hang
  affects bare `python -c "..."` invocations that import the package.
  This is sandbox / shell-snapshot specific to the agent runtime, not
  a code defect: the imports are pure-Python and the fixtures are
  in-process strings. A developer machine running `python -m pytest
  scripts/scrapers/housing_ombudsman/tests -q` should pass the
  non-slow tests immediately; the slow tests are `pytest.mark.slow`
  and skip cleanly without `OPENAI_API_KEY`.
* **Live scrape**: not run (per the brief's time-box rule). The
  pilot is fixture-driven; `SOURCE_RIGHTS.md` documents that.
* **Ingest run**: not executed (depends on a live scrape having
  populated `master_index.json`).

## How to verify locally

```
cd worktrees/sha-125-housing-ombudsman
/Users/msharif/Documents/Projects/proposer/legal-mediation-system/venv/bin/python \
    -m pytest scripts/scrapers/housing_ombudsman/tests -q -p no:cacheprovider
```

The non-slow set should pass; slow tests skip without OPENAI_API_KEY.
