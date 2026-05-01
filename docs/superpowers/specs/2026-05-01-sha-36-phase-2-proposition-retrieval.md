# SHA-36 Phase 2: Proposition PageRank Retrieval Spec

**Status:** Proposed follow-up after PR #15 merge.
**Owner:** Mohamed Sharif
**Base:** `main` after PR #15 merge commit `ea16e53`
**Phase 1 PR:** https://github.com/MSH4R1F/proposer/pull/15

## Purpose

Phase 1 built the proposition KG substrate. Phase 2 turns that substrate into
a measured retrieval mode that can compete with the existing chunk-level RAG
pipeline.

The core idea is simple:

1. Start with a disputed issue from `PredictionEngineV2`.
2. Seed a graph search with issue tags, entities, dates, amounts, and direct
   proposition text matches.
3. Run typed Personalized PageRank over quote-verified propositions and edges.
4. Return a compact, cited set of propositions to the predictor.
5. Evaluate it as an ablation before making it production default.

This is not a rewrite of prediction. It is a new retriever that plugs into the
existing V2 pipeline and must prove itself against the current RAG retriever.

## What Phase 1 Shipped

PR #15 shipped the offline corpus substrate for proposition-grained legal
retrieval. It did not change live user predictions.

Phase 1 delivered:

- Four Postgres tables:
  - `decision_documents`: one row per ingested tribunal decision.
  - `proposition_extraction_runs`: one row per extraction attempt, including
    model, prompt, status, token counts, and rejection counts.
  - `propositions`: quote-verified atomic claims with paragraph refs, issue
    tags, entities, confidence, type, and source span fields.
  - `proposition_edges`: typed links between propositions in the same document.
- Three Postgres enums for proposition type, edge type, and run status.
- Alembic migration `0002_add_proposition_kg.py`.
- Pydantic domain models in `packages/kg_builder/propositions/models.py`.
- Text loading and provenance helpers, reusing the existing PDF extractor.
- LLM proposition extraction with strict quote verification:
  - Every persisted proposition must include a `source_passage`.
  - The source passage must literally appear in the extracted decision text
    after whitespace-normalized matching.
  - Unsupported propositions are rejected before persistence.
- LLM edge extraction over the accepted proposition set.
- Graph validation:
  - reject edges with missing endpoints,
  - reject cross-document edges,
  - de-duplicate parallel edges,
  - avoid invalid support cycles.
- Repository and Unit of Work wiring for async Postgres persistence.
- A corpus selector CLI for deterministic local smoke manifests.
- An ingestion CLI with `--commit`, `--resume`, `--force`, `--dry-run`,
  `--jsonl-report`, and `--mock-response`.
- CI-safe integration tests that exercise manifest to Postgres round trips
  without requiring raw BAILII data.

Local post-merge smoke against 4 real BAILII decisions produced:

| Metric | Value |
|--------|-------|
| Documents persisted | 4 |
| Succeeded extraction runs | 4 |
| Earlier failed retry rows | 3 |
| Propositions persisted | 411 |
| Edges persisted | 178 |
| Orphan edges | 0 |
| Cross-document edges | 0 |

The smoke also found two Phase 1 hardening fixes that should land before
Phase 2 depends on the data:

- Store verified document-level `source_start_char` / `source_end_char`
  offsets on accepted propositions.
- Record per-document token deltas in run rows and JSONL reports, rather than
  cumulative process totals.

## Phase 2 Goals

1. Build a `PropositionRetriever` that returns proposition-level retrieval
   context from Postgres.
2. Use Personalized PageRank over typed proposition edges to capture local
   legal reasoning paths, not just isolated text matches.
3. Keep existing chunk RAG as the baseline and fallback.
4. Add an explicit ablation mode so evaluation can compare:
   - chunk RAG,
   - proposition direct retrieval,
   - proposition PageRank retrieval,
   - hybrid chunk plus proposition retrieval.
5. Preserve cite-or-abstain:
   every proposition shown to the predictor must carry a verifiable quote,
   case reference, paragraph ref when available, and `proposition_id`.
6. Measure retrieval quality before production rollout.

## Non-Goals

- Do not replace the existing RAG path by default.
- Do not build Neo4j or introduce a separate graph database.
- Do not run a full 500-document backfill blindly.
- Do not let PageRank output uncited legal claims.
- Do not make user-facing legal recommendations. Prediction output remains
  informational and conditional.

## Architecture

```text
CaseFile + IssueContext + KGFacts
        |
        v
PropositionSeedSelector
  - issue aliases
  - entity mentions
  - amounts and dates
  - direct proposition text search
        |
        v
PropositionGraphStore (Postgres)
  - candidate propositions
  - typed edges among candidates
  - document metadata
        |
        v
PersonalizedPageRank
  - typed edge weights
  - restart vector from seeds
  - max iteration / convergence cap
        |
        v
PropositionReranker
  - PageRank score
  - issue match
  - recency
  - proposition type diversity
  - document diversity
        |
        v
ContextAssembler
  - compact quote cards
  - grouped citations
  - IssueRetrievalResult-compatible output
        |
        v
PredictionEngineV2
```

## Data Contract

Phase 2 consumes these Phase 1 fields:

| Field | Use |
|-------|-----|
| `proposition_id` | Graph node id and citation key. |
| `document_id` | Grouping, document metadata joins, document diversity. |
| `case_reference` | User-visible citation. |
| `text` | Short proposition claim for ranking and prompt context. |
| `source_passage` | Quote shown to the predictor and UI. |
| `paragraph_ref` | Precise legal citation when available. |
| `source_start_char`, `source_end_char` | Quote relocation and future source viewer. |
| `proposition_type` | Diversity and prompt packing. |
| `issue_tags` | Retrieval filters and seed labels. |
| `entities` | Entity seed matching. |
| `confidence` | Soft ranking feature, not a truth guarantee. |
| `proposition_edges.edge_type` | Typed graph traversal weights. |

The retriever must tolerate older rows with missing offsets but should report
an audit warning. Fresh smoke/backfill runs should have offsets populated.

## Component Design

### 1. Canonical Issue Tags

Phase 1 intentionally allowed flexible issue tags from the extractor. The smoke
showed useful but noisy labels such as `hmo_licensing`, `hmo_licence`, and
`rent_repayment_order`.

Phase 2 adds a canonical issue map:

```python
ISSUE_TAG_ALIASES = {
    DisputeIssue.CLEANING: {"cleaning", "professional_cleaning"},
    DisputeIssue.DAMAGE: {"damage", "repair", "property_condition"},
    DisputeIssue.INVENTORY: {"inventory", "check_in_inventory", "check_out_inventory"},
    DisputeIssue.REDECORATION: {"redecoration", "decoration", "painting"},
    DisputeIssue.FAIR_WEAR_AND_TEAR: {"fair_wear_and_tear", "wear_and_tear"},
    DisputeIssue.DEPOSIT_PROTECTION: {
        "deposit_protection",
        "tenancy_deposit_scheme",
        "prescribed_information",
    },
}
```

This is deliberately conservative. Unknown tags remain searchable as text but
do not become high-weight seeds until reviewed.

### 2. Seed Selection

`PropositionSeedSelector` creates a weighted restart vector.

Seed sources:

| Source | Weight | Notes |
|--------|--------|-------|
| Exact canonical issue tag match | 1.00 | Strongest deterministic signal. |
| Issue alias match | 0.85 | Alias map controls vocabulary drift. |
| Entity match from KG/user facts | 0.75 | Names, property terms, schemes, documents. |
| Monetary amount/date match | 0.65 | Useful for factual analogy, not enough alone. |
| Direct proposition text search | 0.60 | BM25 or SQL text search. |
| Same case as a high-confidence seed | 0.30 | Local expansion only. |

The selector should emit both seed ids and a trace:

```python
{
    "proposition_id": "...",
    "seed_weight": 0.85,
    "seed_reason": "issue_alias: check_in_inventory",
}
```

### 3. Graph Loading

For MVP scale, graph loading can happen in memory from Postgres.

Candidate expansion:

1. Load seed propositions.
2. Load edges among seed documents and neighboring propositions.
3. Add same-document neighbors up to a capped number per document.
4. Cap total graph nodes per issue, default `max_nodes=1500`.

No new database is required. If this becomes slow, add read indexes or a
materialized adjacency table later.

### 4. Typed PageRank

Use Personalized PageRank with restart probability `alpha = 0.15`.

Initial edge weights:

| Edge type | Weight | Rationale |
|-----------|--------|-----------|
| `supports` | 1.00 | Main legal reasoning path. |
| `applies_rule_to_fact` | 1.10 | High value for IRAC-style reasoning. |
| `contradicts` | 0.65 | Useful but should not dominate. |
| `temporal_before` | 0.45 | Good for timelines, weaker for analogies. |
| `cites` | 0.75 | Useful when authority propositions are present. |

Direction matters. Traverse outgoing edges and optionally add a lower-weight
reverse edge for `supports` and `applies_rule_to_fact` so outcome nodes can
surface their supporting facts.

Stop conditions:

- max iterations: 50,
- tolerance: `1e-6`,
- hard timeout per issue: 500ms for graph ranking after graph load.

### 5. Reranking

PageRank is not the final score. It is one feature.

Suggested first scoring blend:

```text
final_score =
  0.35 * pagerank_score
+ 0.25 * issue_match_score
+ 0.15 * text_match_score
+ 0.10 * temporal_relevance
+ 0.10 * proposition_confidence
+ 0.05 * proposition_type_bonus
```

Then apply diversity constraints:

- no more than 4 propositions per document in the final context,
- include at least one `rule` or `authority` proposition when available,
- include at least one `outcome` proposition when available,
- avoid near-duplicate `source_passage` values.

### 6. Context Assembly

The assembled context should be compact enough for the predictor to use
without drowning in graph noise.

Each result should include:

```python
{
    "kind": "proposition",
    "proposition_id": "...",
    "case_reference": "LON_00BG_HMF_2022_0030",
    "year": 2022,
    "region": "LON",
    "paragraph_ref": "42",
    "proposition_type": "rule",
    "text": "...",
    "quote": "...",
    "score": 0.82,
    "score_breakdown": {...},
    "source": {
        "document_id": "...",
        "source_start_char": 1234,
        "source_end_char": 1320,
    },
}
```

For `PredictionEngineV2`, this can initially be adapted into the existing
`IssueRetrievalResult.results` list. Longer term, use a typed union for chunk
results and proposition results.

## Prediction Integration

Add a retrieval strategy enum separate from `PredictionMode`:

```python
class RetrievalStrategy(str, Enum):
    CHUNK_RAG = "chunk_rag"
    PROPOSITION_DIRECT = "proposition_direct"
    PROPOSITION_PAGERANK = "proposition_pagerank"
    HYBRID_CHUNK_PROPOSITION = "hybrid_chunk_proposition"
```

Why separate from `PredictionMode`:

- `PredictionMode` controls KG/RAG ablations.
- `RetrievalStrategy` controls how precedent context is retrieved.
- Keeping them separate avoids turning the mode enum into a combinatorial mess.

Initial rollout:

1. Feature flag default: `chunk_rag`.
2. CLI/eval can request `proposition_pagerank`.
3. API can expose it only behind debug or internal config.
4. Production default remains unchanged until evaluation passes.

## Cite-or-Abstain Rules

Phase 2 must preserve the safety properties of Phase 1.

Hard rules:

- If a proposition lacks `source_passage`, it is not eligible.
- If a proposition lacks `case_reference`, it is not eligible.
- If retrieved proposition count is below `min_cases_required`, mark the issue
  retrieval insufficient.
- The predictor may cite only proposition results included in the retrieval
  context.
- Citation verification must accept proposition citations by `proposition_id`
  or `(case_reference, paragraph_ref, quote)` lookup.

No LLM step may invent a case reference or paragraph ref outside the retrieved
set.

## Evaluation Plan

Phase 2 is successful only if it beats or complements chunk RAG on measured
tasks. It should not be promoted because it feels elegant.

### Datasets

1. **Smoke set:** 4 to 10 real BAILII documents for developer iteration.
2. **Gold set subset:** deposit-dispute cases with manually labeled outcomes.
3. **Hard cases:** multi-issue cases where facts and outcomes are separated
   across paragraphs.
4. **Temporal holdout:** newer decisions reserved for final validation.

### Metrics

| Metric | Gate |
|--------|------|
| Context precision@10 | Better than chunk RAG by at least 10 percent on hard cases. |
| Context recall@10 | Not worse than chunk RAG by more than 5 percent. |
| Citation validity | 100 percent deterministic validity on generated citations. |
| Unsupported proposition rate | 0 persisted unsupported propositions. |
| Outcome accuracy | No regression versus chunk RAG on gold set. |
| Brier score | No regression versus chunk RAG. |
| Latency | Retrieval overhead under 1.5s per case at MVP corpus scale. |
| Cost | No extra LLM cost at retrieval time. |

### Ablation Rows

| Row | Description |
|-----|-------------|
| `chunk_rag` | Current production retrieval baseline. |
| `proposition_direct` | Seeds and direct proposition ranking, no PageRank. |
| `proposition_pagerank` | Seeds plus typed Personalized PageRank. |
| `hybrid_chunk_proposition` | Merge chunk RAG and proposition PageRank contexts. |

The key thesis question is whether graph traversal improves multi-hop legal
retrieval beyond direct proposition matching.

## Backfill Strategy

Do not backfill all documents as the first Phase 2 task.

Recommended sequence:

1. Re-run 4-document smoke with `--force` after the offset and token fixes.
2. Run a 25-document deposit-focused backfill.
3. Audit extraction quality and near-duplicate rate.
4. Run retrieval eval on the 25-document subset.
5. Expand to 100 documents only if eval looks promising.
6. Full corpus backfill only after cost and quality gates are understood.

Backfill reports must include:

- documents attempted,
- succeeded / failed / skipped,
- propositions and edges,
- rejection counts by reason,
- token and cost distribution,
- missing offset count,
- orphan/cross-document edge counts.

## Implementation Plan

### Task 1: Smoke Hardening

- Preserve document-level source offsets in the extractor.
- Store per-document token deltas in ingestion run rows and JSONL reports.
- Add regression tests for both.
- Re-run real BAILII smoke with `--force`.

### Task 2: Read Repository Methods

Add read methods to `PropositionsRepo` or a dedicated query service:

- `search_by_issue_tags(tags, limit)`,
- `search_by_entities(entities, limit)`,
- `search_text(query, limit)`,
- `load_edges_for_documents(document_ids)`,
- `load_propositions_by_ids(ids)`,
- `load_document_metadata(document_ids)`.

### Task 3: Canonical Issue Mapper

- Add canonical issue tag aliases.
- Unit-test common deposit dispute issues.
- Keep unknown tags available as weak text features.

### Task 4: Proposition Retriever Models

Add typed models for:

- seed candidates,
- graph nodes,
- graph edges,
- retrieval results,
- score breakdowns,
- trace metadata.

### Task 5: PageRank Engine

- Implement deterministic in-memory PPR with NumPy.
- Unit-test convergence, isolated nodes, typed weights, and restart behavior.
- Keep graph load and graph rank separate for easier profiling.

### Task 6: Context Assembler

- Build compact proposition cards.
- Enforce document and type diversity.
- Preserve quote, paragraph, and source offsets.

### Task 7: PredictionEngineV2 Integration

- Add retrieval strategy config.
- Keep `chunk_rag` default.
- Add `proposition_pagerank` path for eval and internal debug.
- Do not alter production defaults.

### Task 8: Citation Verifier Extension

- Accept proposition citations by `proposition_id`.
- Verify quoted text against retrieved proposition quote.
- Reject citations outside the retrieved proposition set.

### Task 9: Evaluation Harness

- Add retrieval-only eval first.
- Then run prediction-level eval.
- Report every ablation row in a machine-readable output file.

## Risks

| Risk | Mitigation |
|------|------------|
| Noisy issue tags weaken seeds | Canonical alias map plus weak fallback for unknown tags. |
| Graph traversal amplifies bad edges | Typed weights, confidence weighting, and direct-retrieval ablation. |
| Dense retrieval already wins simple cases | Keep proposition PageRank as a hard-case specialist and hybrid feature. |
| Corpus too small for broad legal claims | Evaluate on held-out cases and report uncertainty. |
| Prompt context gets too fragmented | Context assembler groups by issue and document, with strict top-k caps. |
| Token/cost telemetry wrong | Smoke hardening fixes per-document token deltas before Phase 2. |

## Acceptance Criteria

Phase 2 is ready to merge when:

- `PropositionRetriever` returns cited, quote-backed proposition contexts.
- PageRank retrieval is deterministic in unit tests.
- Existing `chunk_rag` behavior is unchanged by default.
- Citation verifier rejects invented proposition citations.
- Retrieval eval includes the four ablation rows.
- Real smoke shows:
  - 0 orphan edges,
  - 0 cross-document edges,
  - non-null offsets for fresh propositions,
  - per-document token counts,
  - successful retrieval over at least 25 documents.

Phase 2 is ready for production consideration only after the gold-set eval
shows no outcome regression and a measurable retrieval quality gain on hard
multi-hop cases.
