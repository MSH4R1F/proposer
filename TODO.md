# Project TODO List

Tasks and priorities for the legal mediation system development.

---

## 🔥 High Priority

### 1. Reset RAG Index - Adjacent Cases Only
**Status**: TODO  
**Why**: Currently have mixed adjacent + other cases (4,336 cases). Need to focus on adjacent cases only for more relevant results.

**Steps**:
```bash
# 1. Clear existing index
python scripts/rag.py clear

# 2. Re-ingest only adjacent cases
python scripts/rag.py ingest --pdf-dir data/raw/bailii/adjacent-cases

# 3. Verify stats
python scripts/rag.py stats
```

**Expected Results**:
- ~2,400 adjacent cases only
- More focused on deposit protection and related housing issues
- Better retrieval accuracy for target use case

**Note**: Consider keeping a backup of current index before clearing if needed later.

---

### 2. Fix BM25 Index Corruption
**Status**: TODO  
**Issue**: BM25 index is corrupted (84 bytes, division by zero error)

**Solution**:
```bash
# After clearing and re-ingesting, BM25 will rebuild automatically
# Or manually rebuild:
rm data/embeddings/bm25_index.pkl
python scripts/rag.py ingest --pdf-dir data/raw/bailii/adjacent-cases --skip-existing
```

---

## 📋 Medium Priority

### 3. Test RAG Retrieval Quality
**Status**: TODO

**Tasks**:
- [ ] Create test queries (5-10 realistic scenarios)
- [ ] Run retrieval on each query
- [ ] Manually verify top 5 results are relevant
- [ ] Check confidence scores are reasonable
- [ ] Test hybrid search vs. semantic-only comparison

**Example Queries**:
```
- "landlord didn't protect deposit"
- "cleaning costs disputed"
- "damage to carpet fair wear and tear"
- "deposit not protected section 213"
- "rent repayment order"
```

---

### 4. Ingest Remaining Cases
**Status**: TODO  
**Note**: 59 PDFs not yet ingested (if keeping other cases)

```bash
python scripts/rag.py ingest --pdf-dir data/raw/bailii --skip-existing
```

---

## 🔧 Technical Improvements

### 5. Optimize Chunking Strategy
**Status**: TODO

**Current**: 500 tokens/chunk, 50 token overlap
**Evaluate**:
- Is 500 tokens optimal for legal text?
- Should overlap be larger (100 tokens)?
- Test different section-aware chunking

---

### 6. Add Query Interface
**Status**: TODO

**Create**:
- Simple CLI query tool with rich output
- Web interface for testing queries
- Save query history for evaluation

---

### 7. Implement Evaluation Framework
**Status**: TODO

**Metrics**:
- [ ] Create gold standard test set (50-100 cases)
- [ ] Measure outcome prediction accuracy
- [ ] Calculate calibration (Brier score)
- [ ] Track hallucination rate (citations)
- [ ] Compare hybrid vs. semantic-only

---

## 🎯 Knowledge Graph (Future)

### 8. Start KG Builder
**Status**: NOT STARTED

**Tasks**:
- [ ] Design ontology for tenancy disputes
- [ ] Implement fact extraction from tribunal text
- [ ] Build Neo4j schema
- [ ] Test entity extraction accuracy

---

## 🚀 LLM Orchestrator (Future)

### 9. Prediction Engine
**Status**: NOT STARTED

**Tasks**:
- [ ] Design prompt templates
- [ ] Integrate RAG retrieval
- [ ] Generate outcome predictions
- [ ] Create reasoning traces
- [ ] Implement cite-or-abstain rule

---

## 📱 Frontend (Future)

### 10. Web Application
**Status**: NOT STARTED

**Features**:
- User case intake
- Query similar cases
- View predictions
- Mediation interface

---

## 📝 Documentation

### 11. Write User Guide
**Status**: TODO

**Include**:
- How to ingest cases
- How to query the system
- Understanding confidence scores
- Interpreting results

---

### 12. API Documentation
**Status**: TODO

**Document**:
- RAG pipeline endpoints
- Request/response formats
- Example queries
- Error handling

---

## 🧪 Testing

### 13. Unit Tests
**Status**: PARTIAL

**Needed**:
- [ ] PDF extraction tests
- [ ] Chunking tests
- [ ] Embedding tests
- [ ] Retrieval tests
- [ ] Re-ranking tests

---

### 14. Integration Tests
**Status**: TODO

**Tests**:
- [ ] Full pipeline (PDF → chunks → embeddings → retrieval)
- [ ] Query → results validation
- [ ] Confidence calculation accuracy

---

## 💾 Data Management

### 15. Backup Strategy
**Status**: TODO

**Implement**:
- Regular backups of ChromaDB
- Version control for BM25 index
- Document re-ingestion process
- Cost tracking for embeddings

---

## 🔒 Legal Compliance

### 16. Review Legal Disclaimers
**Status**: TODO

**Ensure**:
- All outputs include "not legal advice" disclaimer
- Conditional language used ("likely", "similar cases suggest")
- Clear attribution to source cases
- No definitive legal conclusions

---

## Notes

- **Priority**: Focus on getting adjacent-cases only RAG working first
- **Timeline**: No hard deadlines, learning project
- **Budget**: Keep embedding costs under $5 for now
- **Quality**: Prioritize accuracy over speed of development

---

## Completed ✅

- [x] Build PDF scraper for BAILII
- [x] Extract text from PDFs
- [x] Implement text cleaning and PII redaction
- [x] Create legal-aware chunking
- [x] Set up ChromaDB vector store
- [x] Implement OpenAI embeddings
- [x] Build BM25 keyword index
- [x] Create hybrid retriever (RRF fusion)
- [x] Implement domain-specific re-ranker
- [x] Build CLI interface
- [x] Fix stats command accuracy
- [x] Create diagnostic tools

---

*Last Updated: 2026-01-02*

