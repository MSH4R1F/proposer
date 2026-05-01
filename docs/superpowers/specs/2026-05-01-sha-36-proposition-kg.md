# SHA-36: Proposition KG — Phase 1 Substrate (Design Spec)

**Status:** Skeleton (Task 0 preflight). Full design rationale lands in Task 11.
**Owner:** Mohamed Sharif
**Linear:** SHA-36
**Branch:** `feature/sha-36-proposition-kg`
**Worktree:** `worktrees/sha-36-proposition-kg`
**Base:** `main` @ `1b6248b` (SHA-102 Postgres + UoW + repos already landed)

## Purpose

This document is the design spec for SHA-36 Phase 1: turning tribunal documents into a **proposition-grained substrate** (atomic claims with quote-level provenance, issue tags, entities, and edges) that downstream Phase 2 graph retrieval can consume. Phase 2 (PageRank-driven multi-hop retrieval) is **out of scope** for this PR — see contract section below.

For Task 0 the goal is a skeleton plus the four repo facts and the SOTA basis. Task 11 will expand this with deterministic ID design, prompt-injection defenses, evaluation rubric, and migration plan.

## Branch / Worktree State at Preflight

- Worktree: `worktrees/sha-36-proposition-kg`
- Branch: `feature/sha-36-proposition-kg` (created from `main` @ `1b6248b`)
- `git status --short` at preflight: only `docs/superpowers/plans/2026-05-01-sha-36-proposition-kg.md` untracked (the upstream implementation plan, owned by the orchestrator and not modified here). This spec doc is the only file added by Task 0.
- This is the first commit on the branch.

## Preflight Verification (Task 0)

Before designing on top of these assumptions, the plan's claims about the codebase were verified:

```
$ PYTHONPATH=packages python3 - <<'PY'
from rag_engine.extractors.pdf_extractor import PDFExtractor
from llm_orchestrator.clients.claude_client import ClaudeClient
print("extract_from_pdf:", hasattr(PDFExtractor(), "extract_from_pdf"))
print("generate_structured:", hasattr(ClaudeClient, "generate_structured"))
PY
extract_from_pdf: True
generate_structured: True
```

Both `True`. The plan's preflight assumptions hold; downstream tasks may proceed.

## Repo Facts (load-bearing for downstream tasks)

These four facts are what the implementation tasks must respect. They are recorded here verbatim so that any later assumption that contradicts them is immediately visible as a regression.

1. **`data/raw/bailii` is gitignored — raw PDFs are NOT in the worktree, cannot be assumed in CI.**
   - Confirmed: `.gitignore` contains `data/raw/**/*.pdf` and `data/raw/**/*.docx`.
   - Implication: every test in this stack must either use a fixture PDF checked into `tests/fixtures/`, mock the extractor, or be skipped in CI when raw data is absent. No test may `glob("data/raw/bailii/*.pdf")`.

2. **`rag_engine.extractors.pdf_extractor.PDFExtractor` exposes `extract_from_pdf(path) -> tuple[str, dict]` and `extract_case_document(...)`. It does NOT expose `.extract(...)`.**
   - Implication: code calling `PDFExtractor().extract(path)` will fail at runtime. Use `extract_from_pdf` for raw text + metadata, `extract_case_document` for structured case extraction.

3. **The real LLM client is `llm_orchestrator.clients.claude_client.ClaudeClient`. It exposes `generate(...)` and `generate_structured(...)`. It does NOT expose `complete_json(...)`.**
   - Implication: proposition extraction must call `generate_structured(...)` (or `generate(...)` and parse). Any `complete_json` usage is from a stale design and must be rejected in review.

4. **Existing tests use `db_session` / `db_sessionmaker` fixtures from `apps/api/tests/db/conftest.py`, which creates isolated migrated Postgres DBs.**
   - Confirmed: `apps/api/tests/db/conftest.py` defines `async def db_sessionmaker(postgresql_proc, _migrated_template)` and `async def db_session(db_sessionmaker) -> AsyncIterator[AsyncSession]`.
   - Implication: any new repo / migration test for the proposition KG tables reuses these fixtures rather than spinning up its own Postgres or stubbing SQLAlchemy. New schema must round-trip through the same migrated-template flow.

## SOTA Basis

The Phase 1 substrate design is grounded in five recent results. Each citation includes a one-sentence relevance gloss explaining how it shapes our design.

1. **Dense X Retrieval** — https://arxiv.org/abs/2312.06648
   *Propositions outperform passages as retrieval units under fixed context budget.* This is the primary justification for going proposition-grained at all rather than chunk-grained — under a finite context window, atomic propositions pack more answer-bearing signal per token.

2. **HippoRAG (NeurIPS 2024)** — https://papers.neurips.cc/paper_files/paper/2024/file/6ddc001d07ca4f319af96a3024f6dbd1-Paper-Conference.pdf
   *Offline KG + Personalized PageRank for single-step multi-hop retrieval.* This is the Phase 2 architectural target: the substrate we build in Phase 1 (propositions + entity edges + issue tags) is exactly the input shape HippoRAG's PPR retriever expects, so we build it that way from day one.

3. **GraphRAG-Bench** — https://arxiv.org/abs/2506.05690
   *Graphs help on complex reasoning, can underperform vanilla RAG elsewhere; therefore Phase 2 must be an ablation, not a replacement.* This is why Phase 1 ships the substrate but does not retire dense retrieval — Phase 2 will be evaluated head-to-head against the existing pipeline, not assumed to win.

4. **Stanford/Yale Legal RAG Hallucinations** — https://law.stanford.edu/wp-content/uploads/2024/05/Legal_RAG_Hallucinations.pdf
   *Even commercial legal RAG hallucinates; justifies strict quote-level provenance + abstention.* This is why every proposition stores a verbatim quote span from its source document and an offset, and why the extractor must abstain rather than paraphrase when a span isn't extractable.

5. **RAGAS metrics** — https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/
   *Context precision/recall, faithfulness, answer relevancy as the eval vocabulary that proposition KG should improve.* The Phase 1→Phase 2 ablation will report these RAGAS metrics so improvements are stated in a shared, reproducible vocabulary rather than ad-hoc internal scores.

## Phase 1 Scope (this PR)

Phase 1 builds the substrate only. The expected deliverables across later tasks (sketched here, not designed in detail yet — Task 11 will expand):

- Proposition data model (id, document_id, quote span, offsets, issue_tags, entities).
- Edge model (proposition ↔ proposition, proposition ↔ entity, edge_type).
- Postgres tables + Alembic migration, reusing the `apps/api/src/db/` UoW + repo pattern from SHA-102.
- Extractor pipeline: `PDFExtractor.extract_from_pdf` → segmenter → `ClaudeClient.generate_structured` proposition extraction → repo persistence.
- Tests using `db_session` / `db_sessionmaker`, with a small fixture PDF (NOT relying on `data/raw/bailii`).

Out of scope for Phase 1: PageRank traversal, multi-hop retrieval, integration into the live mediation prediction path. Those are Phase 2.

## Phase 2 PageRank Contract (OUT OF SCOPE for this PR)

Phase 2 is **out of scope** for this PR. This section exists only to fix the data contract Phase 1 must satisfy so that Phase 2 can be added without re-shaping the substrate.

What Phase 2 retrieval will consume from the Phase 1 substrate:

- **Proposition IDs** — stable, deterministic identifiers usable as graph nodes and as keys in a PageRank result vector.
- **`issue_tags`** — per-proposition tags (e.g. cleaning, damage, fair wear and tear) used both as retrieval filters and as candidate seed labels.
- **Entities** — named entities attached to propositions (parties, addresses, monetary amounts, dates) used as **PageRank seed nodes** when a query mentions them.
- **Edge list with `edge_type`** — typed edges (e.g. `supports`, `contradicts`, `mentions_entity`, `same_document`) so Phase 2 can run typed/weighted PPR rather than uniform random walk.
- **`document_id` metadata** — every proposition retains its source document id so retrieved propositions can be re-grouped, cited, and re-ranked at the document level when needed.

Explicitly out of scope for this PR: the PageRank implementation itself, seed-selection heuristics, the retriever interface, and any change to the existing dense-retrieval pipeline.

## Open Questions (deferred to Task 11)

- Deterministic ID scheme for propositions (content hash vs. doc_id + offset vs. composite).
- Prompt-injection hardening for the extraction LLM call (tribunal PDFs are external untrusted input).
- Evaluation rubric: which RAGAS metrics, on what eval set, with what statistical test.
- Migration plan: backfill strategy for the existing ~500 tribunal cases vs. on-demand extraction.
- Cost ceiling per document for `generate_structured` extraction, and the cheap-model triage step (if any).

## References

- Implementation plan (orchestrator-owned, not modified by this spec): `docs/superpowers/plans/2026-05-01-sha-36-proposition-kg.md`
- Prior spec for the underlying persistence layer: `docs/superpowers/specs/2026-04-29-postgres-migration-design.md` (SHA-102)
- `apps/api/tests/db/conftest.py` — DB fixture pattern reused by Phase 1 tests
- `packages/rag_engine/extractors/pdf_extractor.py` — `PDFExtractor`
- `packages/llm_orchestrator/clients/claude_client.py` — `ClaudeClient`
