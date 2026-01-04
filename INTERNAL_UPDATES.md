# Internal Repository Updates

Log of changes, fixes, and improvements made to the legal mediation system.

---

## 2026-01-02 - RAG Engine Stats & Diagnostics

### Issues Fixed
1. **BM25 Index Corruption** 
   - Found BM25 index was corrupted (division by zero error)
   - Only 84 bytes instead of proper size
   - Hybrid search was running on semantic-only (missing keyword component)

2. **Misleading Stats Output**
   - Original `stats` command only sampled 100 random chunks
   - By chance, all 100 were from 2022, showing "Years: [2022]"
   - Created false impression that only 2022 data was indexed
   - **Fixed**: Now scans ALL chunks for accurate statistics

3. **Second Stats Bug - Even Distribution Artifact**
   - After first fix, stats showed exactly 25% per year (500 chunks each)
   - Was only sampling 2,000 chunks spread evenly across 43,776 total
   - **Fixed**: Now performs full scan of all chunks in batches

### Files Modified

#### `packages/rag_engine/vectorstore/chroma_store.py`
- `get_collection_stats()`: Changed from 100-chunk sample to full scan
- Now processes in 5,000-chunk batches for memory efficiency
- Returns detailed distributions: year counts, region counts, case type counts
- Shows unique case count and average chunks per case

#### `packages/rag_engine/cli.py`
- Updated stats display to show:
  - Unique case count
  - Average chunks per case
  - Full year distribution with counts, percentages, and visual bars
  - Region distribution breakdown
  - Top 5 case types

### Scripts Created

#### `scripts/check_rag_years.py`
- Diagnostic script to analyze what's actually in ChromaDB
- Scans all chunks to get accurate year distribution
- Compares indexed cases vs. PDFs on disk
- **Note**: Later deleted after functionality moved to main stats command

#### `scripts/diagnose_ingestion.py`
- Comprehensive diagnostic tool
- Shows full year distribution across all chunks
- Lists PDFs on disk vs. indexed cases
- Identifies un-ingested PDFs

### Current RAG Status (as of 2026-01-02)

**Indexed:**
- **Total chunks**: 43,776
- **Unique cases**: 4,336
- **Average chunks/case**: ~10.1

**Year Distribution:**
- 2020: 9,250 chunks (21.1%)
- 2021: 19,808 chunks (45.2%)
- 2022: 13,226 chunks (30.2%)
- 2023: 1,492 chunks (3.4%)

**Region Distribution:**
- BIR: 12.5%
- CAM: 6.8%
- CHI: 23.0%
- LON: 47.8% (largest)
- MAN: 9.9%

**On Disk:**
- 4,420 PDFs available
- 4,395 unique cases
- 59 PDFs not yet ingested (98.7% complete)

**PDFs by Directory:**
- 2020: 860 PDFs
- 2021: 2,211 PDFs
- 2022: 1,216 PDFs
- 2023: 133 PDFs

### Technical Insights

**Where Year Metadata Comes From:**
1. Primary: `metadata.json` files created by scraper
2. Scraper extracts year from BAILII URL structure: `/PC/2022/case_ref`
3. BAILII organizes by decision/publication year, not filing year
4. Case references may contain different years (e.g., `CHI_45UG_HMF_2021_0039` decided in 2022)
5. Fallback: RAG engine extracts from file path if no metadata

**Why Some Case Refs Show Different Years:**
- Year in case reference = filing/case number year
- Year in metadata = decision/publication year (what we index)
- BAILII publishes by decision year (correct for precedent value)

### Embedding Model Decision

**Current**: `text-embedding-3-small`
- Cost: $0.02 per 1M tokens
- Dimensions: 1,536
- Performance: ~62% on MTEB benchmarks

**Alternative Considered**: `text-embedding-3-large`
- Cost: $0.13 per 1M tokens (6.5x more expensive)
- Dimensions: 3,072
- Performance: ~64.6% on MTEB (only 3.7% better)

**Decision**: Stick with `small` because:
- Hybrid search (BM25 + semantic) adds more value than model size
- Domain re-ranking provides additional boost
- Cost-effective for student project
- Can upgrade later if needed (just re-embed)

### Estimated Costs
- Current indexed: 43,776 chunks × ~500 tokens = ~21.9M tokens
- Cost with small model: ~$0.44
- Cost with large model: ~$2.85
- Queries: negligible (<$0.01 per 1000 queries)

---

## Previous Updates

*(Add earlier updates here as they occur)*


