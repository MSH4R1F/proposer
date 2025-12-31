# RAG Engine for Proposer

**Retrieval-Augmented Generation pipeline for UK tribunal case retrieval**

A production-ready RAG system that retrieves semantically similar tribunal cases to support legal outcome prediction for tenancy deposit disputes.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           RAG PIPELINE ARCHITECTURE                              │
└─────────────────────────────────────────────────────────────────────────────────┘

                              ┌──────────────────┐
                              │   PDF Documents  │
                              │  (BAILII cases)  │
                              └────────┬─────────┘
                                       │
                    ┌──────────────────▼──────────────────┐
                    │         INGESTION PIPELINE          │
                    └──────────────────┬──────────────────┘
                                       │
           ┌───────────────────────────┼───────────────────────────┐
           │                           │                           │
           ▼                           ▼                           ▼
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│  PDF Extractor   │      │   Text Cleaner   │      │  Legal Chunker   │
│    (PyMuPDF)     │─────▶│  (PII Redaction) │─────▶│ (Section-aware)  │
│                  │      │  (Normalization) │      │  (~500 tokens)   │
└──────────────────┘      └──────────────────┘      └────────┬─────────┘
                                                             │
                                                             ▼
                                                  ┌──────────────────┐
                                                  │ OpenAI Embeddings│
                                                  │ (text-embedding- │
                                                  │   3-small)       │
                                                  └────────┬─────────┘
                                                           │
                         ┌─────────────────────────────────┼─────────────────────────────────┐
                         │                                 │                                 │
                         ▼                                 ▼                                 │
              ┌──────────────────┐              ┌──────────────────┐                         │
              │    ChromaDB      │              │   BM25 Index     │                         │
              │  (Vector Store)  │              │ (Keyword Search) │                         │
              │  Semantic Search │              │  Legal Terms     │                         │
              └────────┬─────────┘              └────────┬─────────┘                         │
                       │                                 │                                   │
                       └─────────────┬───────────────────┘                                   │
                                     │                                                       │
                                     ▼                                                       │
                         ┌──────────────────────┐                                            │
                         │   RETRIEVAL QUERY    │◀───────────────────────────────────────────┘
                         │   "case facts..."    │
                         └──────────┬───────────┘
                                    │
           ┌────────────────────────┼────────────────────────┐
           │                        │                        │
           ▼                        ▼                        │
┌──────────────────┐     ┌──────────────────┐               │
│ Semantic Search  │     │   BM25 Search    │               │
│  (Cosine Sim.)   │     │   (TF-IDF)       │               │
└────────┬─────────┘     └────────┬─────────┘               │
         │                        │                          │
         └───────────┬────────────┘                          │
                     │                                       │
                     ▼                                       │
          ┌──────────────────┐                               │
          │  Hybrid Fusion   │                               │
          │ (Reciprocal Rank │                               │
          │    Fusion)       │                               │
          └────────┬─────────┘                               │
                   │                                         │
                   ▼                                         │
          ┌──────────────────┐                               │
          │  Custom Reranker │                               │
          │ - Issue Match    │                               │
          │ - Temporal Score │                               │
          │ - Region Match   │                               │
          │ - Evidence Match │                               │
          └────────┬─────────┘                               │
                   │                                         │
                   ▼                                         │
          ┌──────────────────┐                               │
          │   Uncertainty    │                               │
          │   Detection      │                               │
          │ (Confidence <0.5)│                               │
          └────────┬─────────┘                               │
                   │                                         │
                   ▼                                         │
          ┌──────────────────┐                               │
          │   TOP 5 CASES    │                               │
          │  with scores &   │                               │
          │  explanations    │                               │
          └──────────────────┘
```

---

## Why This Architecture?

### Design Decisions & Justifications

#### 1. **Hybrid Search (Semantic + BM25)**

**Why not semantic-only?**
- Legal documents contain specific terminology ("section 213", "Housing Act 2004") that exact keyword matching handles better
- Semantic search excels at paraphrasing ("deposit not returned" ≈ "landlord withheld security money")
- Combined approach ensures we don't miss cases due to vocabulary mismatch

**Implementation**: Reciprocal Rank Fusion (RRF) with k=60
```
score = 0.7 * (1/(k + semantic_rank)) + 0.3 * (1/(k + bm25_rank))
```

#### 2. **Section-Aware Chunking**

**Why not fixed-size chunks?**
- Tribunal decisions have structure: Background → Facts → Reasoning → Decision
- Mixing sections in one chunk dilutes relevance
- Section metadata enables filtering (e.g., "show me only reasoning sections")

**Implementation**: Regex-based section detection, ~500 token chunks with 50 token overlap

#### 3. **text-embedding-3-small (not large)**

**Why smaller model?**
- Cost: $0.02/1M tokens vs $0.13/1M tokens (6.5x cheaper)
- Performance: Marginal accuracy difference for domain-specific retrieval
- Speed: Faster embedding generation for batch ingestion
- Sufficient for ~500 case corpus (can upgrade for production scale)

#### 4. **ChromaDB (not Pinecone initially)**

**Why start local?**
- Zero cost for prototyping and development
- No network latency during iteration
- Easy to debug and inspect vectors
- Abstract base class allows seamless Pinecone migration

**Future**: `BaseVectorStore` interface makes switching trivial

#### 5. **Custom Reranker**

**Why not just use hybrid scores?**
- Legal domain requires domain-specific relevance:
  - **Issue type match**: Cleaning disputes should match cleaning cases
  - **Temporal relevance**: 2023 cases more relevant than 2018 for current law
  - **Regional preference**: Same tribunal region may have consistent judges
  - **Evidence similarity**: Cases with inventory evidence match inventory queries

#### 6. **Uncertainty Detection**

**Why acknowledge uncertainty?**
- Critical for legal applications—overconfident wrong predictions are dangerous
- Users need to know when to seek professional advice
- Aligns with "Cite or Abstain" principle from CLAUDE.md

**Thresholds**:
- Confidence < 0.5 → Flag as uncertain
- Top semantic score < 0.3 → "No similar cases found"

---

## Components

### Extractors (`extractors/`)

| Component | File | Purpose |
|-----------|------|---------|
| **PDFExtractor** | `pdf_extractor.py` | Extract text from tribunal PDFs using PyMuPDF |
| **TextCleaner** | `text_cleaner.py` | Normalize encoding, redact PII (postcodes, phones) |

### Chunking (`chunking/`)

| Component | File | Purpose |
|-----------|------|---------|
| **LegalChunker** | `legal_chunker.py` | Section-aware document segmentation |

**Section Detection Patterns**:
- Background: `BACKGROUND`, `INTRODUCTION`, `THE APPLICATION`
- Facts: `THE FACTS`, `EVIDENCE`, `FINDINGS OF FACT`
- Reasoning: `REASONS`, `THE TRIBUNAL'S REASONS`, `DISCUSSION`
- Decision: `DECISION`, `DETERMINATION`, `ORDER`, `CONCLUSION`

### Embeddings (`embeddings/`)

| Component | File | Purpose |
|-----------|------|---------|
| **BaseEmbeddings** | `base.py` | Abstract interface for embedding providers |
| **OpenAIEmbeddings** | `openai_embeddings.py` | text-embedding-3-small implementation |

**Features**:
- Async batch processing (50 texts/batch)
- Exponential backoff retry
- Token counting and cost tracking

### Vector Store (`vectorstore/`)

| Component | File | Purpose |
|-----------|------|---------|
| **BaseVectorStore** | `base.py` | Abstract interface (Pinecone-ready) |
| **ChromaStore** | `chroma_store.py` | ChromaDB persistent storage |

**Metadata Fields**:
- `case_reference`: Unique case ID
- `year`: Decision year
- `region`: Tribunal region (LON, CHI, MAN, etc.)
- `case_type`: Case type code (HNA, HMF, etc.)
- `section_type`: background/facts/reasoning/decision

### Retrieval (`retrieval/`)

| Component | File | Purpose |
|-----------|------|---------|
| **BM25Index** | `bm25_index.py` | Keyword-based search using rank-bm25 |
| **HybridRetriever** | `hybrid_retriever.py` | RRF fusion of semantic + BM25 |
| **Reranker** | `reranker.py` | Domain-specific re-ranking |

**Reranking Weights** (configurable):
```python
WEIGHTS = {
    "issue_match": 0.4,    # Most important
    "temporal": 0.2,       # Newer cases preferred
    "region": 0.1,         # Same region slight boost
    "evidence": 0.2,       # Evidence type similarity
    "original_score": 0.1, # Preserve hybrid ranking
}
```

### Pipeline (`pipeline.py`)

The main orchestrator that coordinates all components:

```python
from rag_engine import RAGPipeline, RAGConfig

config = RAGConfig.from_env()
pipeline = RAGPipeline(config)

# Ingest PDFs
await pipeline.ingest(pdf_dir="data/raw/bailii")

# Query for similar cases
result = await pipeline.retrieve(
    query="tenant claims deposit not protected within 30 days",
    top_k=5
)

# Check confidence
if result.is_uncertain:
    print(f"Warning: {result.uncertainty_reason}")
```

---

## Usage

### CLI Commands

```bash
# Set your OpenAI API key
export OPENAI_API_KEY=sk-your-key-here

# Ingest all PDFs from BAILII scraper output
python scripts/rag.py ingest --pdf-dir data/raw/bailii

# Query the index
python scripts/rag.py query "tenant deposit not protected section 213"

# Query with filters
python scripts/rag.py query "cleaning deduction unfair" --region LON --year 2023

# Output as JSON
python scripts/rag.py query "no inventory damage claim" --json-output

# View index statistics
python scripts/rag.py stats

# Test PDF extraction
python scripts/rag.py test-extract data/raw/bailii/adjacent-cases/2023/LON_00BK_HMF_2022_0227/decision.pdf

# Clear and rebuild index
python scripts/rag.py clear
python scripts/rag.py ingest --pdf-dir data/raw/bailii
```

### Python API

```python
import asyncio
from rag_engine import RAGPipeline, RAGConfig

async def main():
    # Initialize
    config = RAGConfig(
        openai_api_key="sk-...",
        chunk_size=500,
        chunk_overlap=50,
        semantic_weight=0.7,  # vs 0.3 for BM25
    )
    pipeline = RAGPipeline(config)

    # Ingest documents
    stats = await pipeline.ingest(pdf_dir="data/raw/bailii")
    print(f"Ingested {stats['chunks_created']} chunks")

    # Query
    result = await pipeline.retrieve(
        query="landlord claims professional cleaning but no evidence",
        top_k=5,
        where={"year": {"$gte": 2020}},  # Filter to recent cases
        query_region="LON"  # Boost London cases
    )

    # Process results
    for r in result.results:
        print(f"{r.case_reference} ({r.year})")
        print(f"  Score: {r.combined_score:.4f}")
        print(f"  Why: {r.relevance_explanation}")
        print(f"  Preview: {r.chunk_text[:200]}...")

asyncio.run(main())
```

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes | - | OpenAI API key for embeddings |
| `DATA_DIR` | No | `./data` | Base data directory |
| `CHROMA_PERSIST_DIR` | No | `./data/embeddings` | ChromaDB storage path |

### RAGConfig Options

```python
class RAGConfig:
    # Embedding
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_batch_size: int = 50

    # Chunking
    chunk_size: int = 500      # tokens
    chunk_overlap: int = 50    # tokens

    # Retrieval
    initial_retrieval_k: int = 20    # Candidates before reranking
    final_top_k: int = 5             # Final results
    rrf_k: int = 60                  # RRF parameter
    semantic_weight: float = 0.7     # vs 1-this for BM25

    # Confidence
    min_confidence_threshold: float = 0.5
    min_similarity_threshold: float = 0.3
```

---

## Data Flow

### Ingestion Flow

```
PDF File
    │
    ├── PDFExtractor.extract_case_document()
    │       └── Returns: CaseDocument with full_text, metadata
    │
    ├── TextCleaner.clean()
    │       └── Returns: Cleaned text, PII redacted
    │
    ├── LegalChunker.chunk_document()
    │       └── Returns: List[DocumentChunk] with sections
    │
    ├── OpenAIEmbeddings.embed_texts()
    │       └── Returns: List[List[float]] embeddings
    │
    ├── ChromaStore.add_chunks()
    │       └── Stores: vectors + metadata
    │
    └── BM25Index.build_index()
            └── Stores: tokenized documents for keyword search
```

### Query Flow

```
Query String
    │
    ├── OpenAIEmbeddings.embed_query()
    │       └── Returns: query embedding vector
    │
    ├── HybridRetriever.retrieve()
    │   ├── ChromaStore.query() → semantic results
    │   ├── BM25Index.search() → keyword results
    │   └── RRF Fusion → combined candidates
    │
    ├── Reranker.rerank()
    │       └── Returns: domain-adjusted rankings
    │
    └── Confidence Calculation
            └── Returns: QueryResult with is_uncertain flag
```

---

## Performance Characteristics

### Expected Metrics

| Metric | Target | Notes |
|--------|--------|-------|
| Ingestion Speed | ~10 PDFs/min | Depends on PDF size, OpenAI rate limits |
| Query Latency | <2 seconds | For 5 results from ~500 cases |
| Embedding Cost | ~$0.01 per case | Average 2,000 tokens/case |
| Storage | ~50MB | ChromaDB for 500 cases |

### Scalability Notes

- **Current**: Optimized for ~500 cases (thesis MVP)
- **Future**: For production (10k+ cases):
  - Migrate to Pinecone for managed scaling
  - Add embedding caching layer
  - Consider async ingestion queue

---

## Further Improvements

### Short-term (Sprint 2)

- [ ] **Cross-encoder reranking**: Use a small transformer model for final reranking
- [ ] **Query expansion**: Automatically expand legal terms (e.g., "s.213" → "section 213")
- [ ] **Caching**: Redis cache for frequent queries
- [ ] **Batch embedding optimization**: Parallel API calls within rate limits

### Medium-term (Sprint 3-4)

- [ ] **Fine-tuned embeddings**: Train on legal corpus for domain adaptation
- [ ] **Learned reranking**: Train reranker on user feedback (clicked cases)
- [ ] **Multi-hop retrieval**: Follow citation chains between cases
- [ ] **Temporal weighting**: Learn optimal decay function from outcomes

### Long-term (Production)

- [ ] **Pinecone migration**: Managed vector DB with filtering
- [ ] **Embedding versioning**: Track model changes, re-embed on update
- [ ] **A/B testing**: Compare retrieval strategies on real queries
- [ ] **Feedback loop**: Use settlement outcomes to improve retrieval

---

## Troubleshooting

### Common Issues

**"OpenAI API key is required"**
```bash
export OPENAI_API_KEY=sk-your-key-here
```

**"No similar cases found"**
- Index may be empty—run `python scripts/rag.py stats` to check
- Query may be too specific—try broader terms
- Check BM25 index is built: `stats["bm25"]["indexed_documents"]`

**Slow ingestion**
- OpenAI rate limits: reduce `embedding_batch_size`
- Large PDFs: some tribunal decisions are 50+ pages
- Network issues: check connectivity

**Low confidence scores**
- Expected for novel cases not in corpus
- Consider expanding data sources (Housing Ombudsman, TDS)
- Check if query matches indexed case types

---

## Testing

```bash
# Run syntax checks
python3 -m py_compile packages/rag_engine/*.py

# Test PDF extraction
python scripts/rag.py test-extract data/raw/bailii/.../decision.pdf

# Test full pipeline (requires OPENAI_API_KEY)
python scripts/rag.py ingest --pdf-dir data/raw/bailii --batch-size 5
python scripts/rag.py query "deposit protection failure"
```

---

## License

MIT License - see [LICENSE](../../LICENSE) for details.

---

**Built for Proposer** - Bridging the justice gap with transparent, legally-grounded AI.
