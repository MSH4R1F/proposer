# Internal Repository Updates

Log of changes, fixes, and improvements made to the legal mediation system.

---

## 2026-01-05 - Next.js Frontend Implementation

### Overview

Implemented complete Next.js 14+ frontend with shadcn/ui for the legal mediation system:
- **Chat Interface**: 10-stage conversational intake with role selection
- **Prediction Display**: Full results page with reasoning traces and citations

### Tech Stack

- **Framework**: Next.js 14+ (App Router)
- **UI Library**: shadcn/ui + Tailwind CSS
- **Language**: TypeScript
- **State Management**: React hooks + localStorage

### New Package Created: `apps/web/`

```
apps/web/
├── app/
│   ├── layout.tsx              # Root layout with Inter font
│   ├── globals.css             # Tailwind + CSS variables
│   ├── providers.tsx           # Client providers
│   ├── page.tsx                # Landing page
│   ├── not-found.tsx           # 404 page
│   ├── (chat)/
│   │   ├── layout.tsx          # Chat layout
│   │   ├── page.tsx            # New session
│   │   └── [sessionId]/page.tsx # Resume session
│   └── prediction/
│       └── [caseId]/page.tsx   # Prediction results
├── components/
│   ├── ui/                     # 11 shadcn components
│   ├── chat/                   # 9 chat components
│   ├── prediction/             # 12 prediction components
│   └── shared/                 # 5 shared components
├── lib/
│   ├── api/                    # API client
│   ├── hooks/                  # React hooks
│   ├── types/                  # TypeScript types
│   ├── constants/              # Stage mappings
│   └── utils/                  # Formatters, storage
└── [config files]
```

### Key Components

#### Chat Components (9 files)
- `ChatContainer.tsx` - Main wrapper with state management
- `ChatHeader.tsx` - Session info, stage, completeness
- `MessageList.tsx` - Scrollable message container
- `MessageBubble.tsx` - User/assistant message styling
- `ChatInput.tsx` - Input field with send button
- `RoleSelector.tsx` - Tenant/Landlord selection buttons
- `ProgressIndicator.tsx` - 10-stage visual stepper
- `CompletenessBar.tsx` - Progress percentage bar
- `TypingIndicator.tsx` - Loading animation

#### Prediction Components (12 files)
- `PredictionCard.tsx` - Main results wrapper
- `OutcomeDisplay.tsx` - Win/Loss/Split visualization
- `ConfidenceGauge.tsx` - Circular confidence meter
- `SettlementRange.tsx` - Financial summary
- `IssuePredictionList.tsx` - Per-issue breakdown
- `IssuePredictionCard.tsx` - Single issue card
- `ReasoningTrace.tsx` - Expandable reasoning steps
- `ReasoningStep.tsx` - Single step with citations
- `CitationCard.tsx` - Case citation display
- `StrengthsWeaknesses.tsx` - Key points lists
- `LegalDisclaimer.tsx` - Prominent warning box
- `PredictionSkeleton.tsx` - Loading skeleton

### API Integration

Frontend integrates with FastAPI backend at `http://localhost:8000`:

```typescript
// Chat flow
POST /chat/start           → { session_id, greeting, stage }
POST /chat/set-role        → { response, stage, completeness, case_file }
POST /chat/message         → { response, stage, completeness, case_file }
GET  /chat/session/{id}    → { session_id, stage, completeness, messages }

// Predictions
POST /predictions/generate → { prediction_id, overall_outcome, confidence, ... }
```

### Key Features

1. **Landing Page** (`/`)
   - Hero section with value proposition
   - Feature cards explaining the process
   - Statistics (500+ cases, 75% accuracy, 10 min)
   - Call-to-action buttons

2. **Chat Interface** (`/chat`)
   - Role selection buttons after greeting
   - Progress indicator showing 10 stages
   - Completeness bar (0-100%)
   - Auto-scroll to new messages
   - Session persistence via localStorage

3. **Prediction Display** (`/prediction/[caseId]`)
   - Overall outcome with confidence gauge
   - Settlement range display
   - Key strengths/weaknesses lists
   - Per-issue breakdown with reasoning
   - Expandable reasoning trace
   - Case citations with quotes
   - Legal disclaimer prominently displayed

### How to Run

```bash
cd apps/web
npm install
npm run dev
# Visit http://localhost:3000
```

Ensure FastAPI backend is running at `http://localhost:8000`.

### Files Created

**Total: 60+ files**
- Configuration: 8 files
- App pages: 6 files
- Types/API/Utils: 12 files
- UI components: 11 files
- Chat components: 9 files
- Prediction components: 12 files
- Shared components: 5 files

---

## 2026-01-05 - LLM Orchestrator, Knowledge Graph & API Implementation

### Overview

Implemented the complete prediction engine stack:
- **LLM Orchestrator**: Conversational intake agents with Claude API
- **Knowledge Graph Builder**: JSON-based structured case representation
- **FastAPI Application**: REST API with chat, evidence, and prediction endpoints

### New Packages Created

#### 1. LLM Orchestrator (`packages/llm_orchestrator/`)

**Core Data Models:**
- `models/case_file.py` - CaseFile with PropertyDetails, TenancyDetails, EvidenceItem, ClaimedAmount
- `models/conversation.py` - ConversationState, Message, IntakeStage (10 stages)
- `models/prediction.py` - PredictionResult, ReasoningStep, Citation, IssuePrediction

**Clients:**
- `clients/claude_client.py` - Anthropic API integration with fallback, retry, cost tracking

**Agents:**
- `agents/intake_agent.py` - 10-stage conversational intake with role detection
- `agents/prediction_agent.py` - RAG + LLM synthesis with cite-or-abstain rule

**Extractors:**
- `extractors/fact_extractor.py` - LLM-based structured fact extraction from conversation
- `extractors/evidence_processor.py` - PDF text extraction, image description

**Prompt Templates:**
- `prompts/tenant_intake.py` - Tenant interview flow (10 stages)
- `prompts/landlord_intake.py` - Landlord interview flow (10 stages)
- `prompts/extraction.py` - Fact extraction with confidence scoring
- `prompts/prediction.py` - Prediction synthesis with JSON schema output

**CLI:**
- `cli.py` - Interactive chat interface for testing intake flow

#### 2. Knowledge Graph Builder (`packages/kg_builder/`)

**Node Types:**
- PartyNode (tenant, landlord, agent)
- PropertyNode (address, type, region)
- LeaseNode (dates, rent, deposit)
- EvidenceNode (document, photo, statement)
- EventNode (timeline events)
- IssueNode (cleaning, damage, deposit_protection)
- ClaimedAmountNode (monetary claims)

**Edge Types:**
- Evidence_Supports, Event_Before, Party_Claims, Evidence_Contradicts
- Issue_Raised_By, Claim_For_Issue, Party_Has_Lease

**Storage:**
- JSON-based file storage (Neo4j-ready migration path)

**Validators:**
- Temporal logic validation (events in order)
- Evidence chain validation (claims have supporting evidence)

#### 3. FastAPI Application (`apps/api/`)

**Routers:**
- `/chat/start` - Start new intake session
- `/chat/message` - Send message, receive response
- `/chat/session/{id}` - Get session state
- `/evidence/upload/{case_id}` - Upload evidence to Supabase
- `/predictions/generate` - Generate outcome prediction
- `/cases/{case_id}` - Case management

**Services:**
- `intake_service.py` - Session management, conversation orchestration
- `prediction_service.py` - RAG + KG + LLM prediction pipeline
- `storage_service.py` - Supabase/local file storage with fallback

### Intake Flow (10 Stages)

```
1. GREETING         - Welcome and role detection
2. ROLE_IDENTIFICATION - Confirm tenant/landlord
3. BASIC_DETAILS    - Property address, type
4. TENANCY_DETAILS  - Start/end dates, rent
5. DEPOSIT_DETAILS  - Amount, protection status, scheme
6. ISSUE_IDENTIFICATION - What's disputed
7. EVIDENCE_COLLECTION - Upload/describe evidence
8. CLAIM_AMOUNTS    - Specific deductions disputed
9. NARRATIVE        - Full story in their words
10. CONFIRMATION    - Review and confirm
```

### Key Design Decisions

1. **Separate Flows**: Tenant and landlord have different prompt templates
2. **JSON-based KG**: MVP approach, can migrate to Neo4j later
3. **Cite-or-Abstain**: Predictions must cite retrieved cases or mark as uncertain
4. **Supabase Storage**: Cloud storage for evidence files with local fallback
5. **Dependency Injection**: Services use singleton pattern for efficiency

### Dependencies Added

```
anthropic>=0.39.0      # Claude API
supabase>=2.0.0        # Cloud storage
python-multipart>=0.0.6 # File uploads
fastapi>=0.109.0       # API framework
uvicorn>=0.27.0        # ASGI server
```

### Scripts Added

- `scripts/intake.py` - CLI runner for intake agent testing
- `scripts/api.py` - FastAPI server runner

### How to Test

**CLI Intake Testing:**
```bash
python scripts/intake.py chat
```

**API Server:**
```bash
python scripts/api.py
# Visit http://localhost:8000/docs
```

### Integration with RAG

The PredictionEngine integrates with existing RAG pipeline:
1. Builds query from CaseFile structured data
2. Retrieves similar cases via RAGPipeline.retrieve()
3. Checks uncertainty flag (cite-or-abstain)
4. Synthesizes prediction with Claude API
5. Generates reasoning trace with citations

### Next Steps

- Reset RAG index to adjacent cases only (TODO #1)
- Add comprehensive unit tests for new packages
- Implement evaluation framework with gold standard test cases

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


