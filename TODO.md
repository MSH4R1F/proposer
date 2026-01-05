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
**Status**: ✅ DONE
**Issue**: BM25 index was corrupted (84 bytes, division by zero error)

**Solution Applied**:
```bash
# Created rebuild script that extracts from ChromaDB:
python scripts/rebuild_bm25.py --lite-mode

# Result: 43,776 chunks indexed, 4,336 unique cases, 176 MB index
```

**Also Fixed**: BM25 lite mode metadata (year, region, case_type fields were missing)

---

## 📋 Medium Priority

### 3. Test RAG Retrieval Quality
**Status**: ✅ DONE

**Tasks**:
- [x] Create test queries (5-10 realistic scenarios)
- [x] Run retrieval on each query
- [x] Manually verify top 5 results are relevant
- [x] Check confidence scores are reasonable
- [x] Test hybrid search vs. semantic-only comparison

**Results**:
```
- Created scripts/test_rag_quality.py for automated evaluation
- 5 test queries run successfully
- 75.3% average confidence score
- 100% topic precision (top 5 results)
- 88% case type precision
- Hybrid search working correctly
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

## 🎯 Knowledge Graph

### 8. Knowledge Graph Builder
**Status**: ✅ DONE

**Completed**:
- [x] Design ontology for tenancy disputes (Party, Lease, Evidence, Event, Issue, ClaimedAmount)
- [x] Implement GraphBuilder (CaseFile → KnowledgeGraph conversion)
- [x] Build JSON-based storage (Neo4j-ready migration path)
- [x] Implement validators (temporal logic, evidence chain validation)

**Package**: `packages/kg_builder/`

---

## 🚀 LLM Orchestrator

### 9. Prediction Engine & Intake Agent
**Status**: ✅ DONE

**Completed**:
- [x] Design prompt templates (tenant/landlord interview flows)
- [x] Implement Claude client with Anthropic SDK
- [x] Build conversational intake agent (10-stage flow)
- [x] Implement fact extractor (LLM-based structured extraction)
- [x] Integrate RAG retrieval with prediction engine
- [x] Generate outcome predictions with reasoning traces
- [x] Implement cite-or-abstain rule
- [x] Add trigger button in UI to call LLM Orchestrator from FastAPI
- [ ] Refactor role identification logic in intake agent to work with button-triggered flows (i.e., explicit API support for detecting landlord vs tenant)

**Package**: `packages/llm_orchestrator/`

**Test with**:
```bash
python scripts/intake.py chat
```

---

## 🌐 API Layer

### 10. FastAPI Application
**Status**: ✅ DONE

**Completed**:
- [x] Set up FastAPI in `apps/api/`
- [x] Implement chat endpoints (`/chat/start`, `/chat/message`)
- [x] Implement evidence upload (`/evidence/upload/{case_id}`)
- [x] Implement prediction endpoints (`/predictions/generate`)
- [x] Implement case management (`/cases/{case_id}`)
- [x] Supabase storage integration (with local fallback)

**Run with**:
```bash
python scripts/api.py
# Visit http://localhost:8000/docs
```

---

## 📱 Frontend (Future)

### 11. Web Application
**Status**: TODO

**Features**:
- User case intake (chat interface)
- Query similar cases
- View predictions with reasoning traces
- Mediation interface

---

## 📝 Documentation

### 11. Write User Guide
**Status**: ✅ DONE

**Location**: `docs/USER_GUIDE.md`

**Includes**:
- How to ingest cases
- How to query the system
- Understanding confidence scores
- Interpreting results

---

### 12. API Documentation
**Status**: ✅ DONE

**Location**: `docs/API_DOCUMENTATION.md`

**Documents**:
- RAG pipeline endpoints
- Request/response formats
- Example queries
- Error handling

**Package READMEs**:
- `packages/llm_orchestrator/README.md`
- `packages/kg_builder/README.md`
- `apps/api/README.md`

---

## 🧪 Testing

### 13. Unit Tests
**Status**: ✅ DONE

**Completed** (141 tests total in `packages/rag_engine/tests/`):
- [x] Config and data model tests (19 tests)
- [x] Text cleaning and PII redaction tests (21 tests)
- [x] Legal chunking tests (17 tests)
- [x] BM25 index tests (23 tests)
- [x] Re-ranking tests (18 tests)
- [x] Hybrid retriever tests (14 tests)
- [x] Pipeline tests (16 tests)
- [x] Retrieval quality tests (13 tests)

**Run with**: `python scripts/run_tests.py` or `pytest packages/rag_engine/tests/`

---

### 14. Integration Tests
**Status**: ✅ DONE

**Tests** (included in test suite):
- [x] Full pipeline (PDF → chunks → embeddings → retrieval)
- [x] Query → results validation
- [x] Confidence calculation accuracy

**Note**: Integration tests use `@pytest.mark.integration` marker. Run with `python scripts/run_tests.py --integration`

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
- [x] Fix BM25 index corruption (rebuilt from ChromaDB, 43,776 chunks)
- [x] Fix BM25 lite mode metadata (year, region, case_type)
- [x] Test RAG retrieval quality (75.3% avg confidence, 100% topic precision)
- [x] Create comprehensive test suite (141 tests)
- [x] Create BM25 rebuild script (`scripts/rebuild_bm25.py`)
- [x] Create RAG quality test script (`scripts/test_rag_quality.py`)
- [x] Create test runner script (`scripts/run_tests.py`)
- [x] Write User Guide (`docs/USER_GUIDE.md`)
- [x] Write API Documentation (`docs/API_DOCUMENTATION.md`)
- [x] Create package READMEs with architecture diagrams

---

*Last Updated: 2026-01-05*

