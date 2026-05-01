# Legal Mediation System - Architecture Overview

This document provides a comprehensive overview of the Proposer platform architecture, showing how the frontend (Next.js), backend (FastAPI), and core packages (RAG, KG, LLM) work together.

## System Architecture

```mermaid
graph TB
    %% Frontend Layer
    subgraph Frontend["🌐 Frontend (Next.js 16 App Router)"]
        HomePage["Home Page<br/>/"]
        ChatListPage["Chat List<br/>/chat"]
        ChatSessionPage["Chat Session<br/>/chat/[sessionId]"]
        PredictionPage["Prediction View<br/>/prediction/[caseId]"]
        AdminPage["Admin<br/>/admin"]
        
        subgraph Components["React Components"]
            ChatContainer["ChatContainer"]
            IntakeSidebar["IntakeSidebar"]
            MessageList["MessageList"]
            PredictionViewer["PredictionViewer"]
            ReasoningTrace["ReasoningTrace"]
        end
        
        subgraph APIClients["API Client Layer"]
            ChatAPIClient["chatApi"]
            PredictionsAPIClient["predictionsApi"]
            APIClient["api (fetch wrapper)"]
        end
    end

    %% API Layer
    subgraph Backend["⚙️ Backend API (FastAPI)"]
        MainApp["main.py<br/>FastAPI App"]
        
        subgraph Routers["API Routers (Endpoints)"]
            ChatRouter["/chat<br/>• POST /start<br/>• POST /message<br/>• POST /set-role<br/>• GET /session/:id<br/>• DELETE /session/:id<br/>• GET /sessions"]
            PredictionsRouter["/predictions<br/>• POST /generate<br/>• GET /:id<br/>• GET /case/:caseId"]
            DisputesRouter["/disputes<br/>• POST /create<br/>• POST /validate-invite<br/>• POST /join<br/>• GET /:id"]
            EvidenceRouter["/evidence<br/>• POST /upload/:caseId<br/>• GET /:caseId<br/>• DELETE /:evidenceId"]
            CasesRouter["/cases<br/>• GET /:caseId<br/>• GET /"]
        end
        
        subgraph Services["Service Layer"]
            IntakeService["IntakeService<br/>• Session Management<br/>• Conversation Flow<br/>• Case File Building<br/>• Postgres + UoW"]
            PredictionService["PredictionService<br/>• Prediction Generation<br/>• RAG Integration<br/>• KG Integration<br/>• Postgres + UoW"]
            DisputeService["DisputeService<br/>• Dispute Creation<br/>• Invite Codes<br/>• Party Linking<br/>• Postgres + UoW"]
            StorageService["StorageService<br/>• File Uploads<br/>• Evidence Processing<br/>• Postgres + UoW"]
        end
    end

    %% Core Packages Layer
    subgraph Packages["📦 Core Packages (Python)"]
        subgraph LLMOrchestrator["llm_orchestrator/"]
            IntakeAgent["IntakeAgent<br/>• Dynamic Questioning<br/>• Context Awareness<br/>• Completeness Tracking"]
            PredictionAgent["PredictionEngine<br/>• Prediction Synthesis<br/>• Reasoning Trace<br/>• Citation Generation"]
            ClaudeClient["ClaudeClient<br/>• Anthropic API<br/>• Structured Outputs<br/>• Error Handling"]
            FactExtractor["FactExtractor<br/>• Entity Extraction<br/>• Evidence Processing"]
        end
        
        subgraph KGBuilder["kg_builder/"]
            GraphBuilder["GraphBuilder<br/>• Node Creation<br/>• Edge Validation<br/>• Constraint Checking"]
            KGModels["KG Models<br/>• Nodes (Party, Evidence, Issue)<br/>• Edges (Supports, OccurredBefore)<br/>• Validators"]
            JSONStore["JSONGraphStore<br/>• Persistence<br/>• Retrieval"]
        end
        
        subgraph RAGEngine["rag_engine/"]
            RAGPipeline["RAGPipeline<br/>• Query Processing<br/>• Orchestration"]
            HybridRetriever["HybridRetriever<br/>• BM25 (keyword)<br/>• Semantic Search<br/>• Weighted Fusion"]
            ChromaStore["ChromaStore<br/>• Vector DB<br/>• Embeddings"]
            Reranker["Reranker<br/>• Relevance Scoring<br/>• Context Filtering"]
            LegalChunker["LegalChunker<br/>• Section Detection<br/>• Smart Chunking"]
        end
    end

    %% Data Layer
    subgraph DataLayer["💾 Data & Storage"]
        subgraph FileSystem["Local File System (pre-SHA-102 / archive)"]
            SessionsDir["data/sessions/<br/>Session JSON files"]
            KGDir["data/knowledge_graphs/<br/>KG JSON files"]
            PredictionsDir["data/predictions/<br/>Prediction JSON files"]
            DisputesDir["data/disputes/<br/>Dispute JSON files"]
        end
        
        subgraph PostgresDB["Primary Database (SHA-102)"]
            PostgresNode["Postgres 16<br/>13 tables · 15 enums<br/>via UoW + Repositories<br/>Alembic migrations"]
        end
        
        subgraph VectorDB["Vector Database"]
            ChromaDB["ChromaDB<br/>• Embeddings<br/>• BM25 Index<br/>• data/embeddings/"]
        end
        
        subgraph ExternalStorage["External Storage"]
            Supabase["Supabase<br/>• Storage Buckets (Evidence)"]
        end
        
        subgraph CaseData["Case Data"]
            TribunalCases["Tribunal Decisions<br/>data/raw/bailii/<br/>~500+ PDFs"]
        end
    end

    %% External Services
    subgraph External["☁️ External Services"]
        Anthropic["Anthropic API<br/>Claude 3.5 Sonnet/Haiku"]
        OpenAI["OpenAI API<br/>text-embedding-3-large"]
    end

    %% Frontend Connections
    ChatSessionPage --> ChatContainer
    ChatSessionPage --> IntakeSidebar
    PredictionPage --> PredictionViewer
    PredictionViewer --> ReasoningTrace
    
    ChatContainer --> ChatAPIClient
    IntakeSidebar --> ChatAPIClient
    PredictionViewer --> PredictionsAPIClient
    
    ChatAPIClient --> APIClient
    PredictionsAPIClient --> APIClient
    APIClient -->|"HTTP/JSON"| MainApp

    %% Backend Router to Service Connections
    MainApp --> ChatRouter
    MainApp --> PredictionsRouter
    MainApp --> DisputesRouter
    MainApp --> EvidenceRouter
    MainApp --> CasesRouter
    
    ChatRouter --> IntakeService
    ChatRouter --> DisputeService
    PredictionsRouter --> PredictionService
    DisputesRouter --> DisputeService
    EvidenceRouter --> StorageService
    CasesRouter --> IntakeService

    %% Service to Package Connections
    IntakeService --> IntakeAgent
    IntakeService --> FactExtractor
    IntakeService --> GraphBuilder
    
    PredictionService --> PredictionAgent
    PredictionService --> RAGPipeline
    PredictionService --> GraphBuilder
    
    DisputeService --> GraphBuilder

    %% LLM Orchestrator Internal Connections
    IntakeAgent --> ClaudeClient
    PredictionAgent --> ClaudeClient
    PredictionAgent --> RAGPipeline
    
    %% RAG Engine Internal Connections
    RAGPipeline --> HybridRetriever
    RAGPipeline --> Reranker
    HybridRetriever --> ChromaStore
    
    %% KG Builder Connections
    GraphBuilder --> KGModels
    GraphBuilder --> JSONStore

    %% Data Persistence Connections (SHA-102: services now use Postgres via UoW)
    IntakeService -.->|"UoW / Repo"| PostgresNode
    DisputeService -.->|"UoW / Repo"| PostgresNode
    PredictionService -.->|"UoW / Repo"| PostgresNode
    GraphBuilder -.->|"UoW / Repo"| PostgresNode
    ChromaStore -.->|"Read/Write"| ChromaDB
    HybridRetriever -.->|"Query"| ChromaDB
    StorageService -.->|"Upload"| Supabase
    RAGPipeline -.->|"Load"| TribunalCases

    %% External Service Connections
    ClaudeClient -->|"API Calls"| Anthropic
    ChromaStore -->|"Generate Embeddings"| OpenAI

    %% Styling
    classDef frontend fill:#3b82f6,stroke:#1e40af,color:#fff
    classDef backend fill:#8b5cf6,stroke:#6d28d9,color:#fff
    classDef package fill:#10b981,stroke:#059669,color:#fff
    classDef data fill:#f59e0b,stroke:#d97706,color:#fff
    classDef external fill:#ef4444,stroke:#dc2626,color:#fff
    
    class HomePage,ChatListPage,ChatSessionPage,PredictionPage,AdminPage,ChatContainer,IntakeSidebar,MessageList,PredictionViewer,ReasoningTrace,ChatAPIClient,PredictionsAPIClient,APIClient frontend
    class MainApp,ChatRouter,PredictionsRouter,DisputesRouter,EvidenceRouter,CasesRouter,IntakeService,PredictionService,DisputeService,StorageService backend
    class IntakeAgent,PredictionAgent,ClaudeClient,FactExtractor,GraphBuilder,KGModels,JSONStore,RAGPipeline,HybridRetriever,ChromaStore,Reranker,LegalChunker package
    class SessionsDir,KGDir,PredictionsDir,DisputesDir,ChromaDB,Supabase,TribunalCases,PostgresNode data
    class Anthropic,OpenAI external
```

## Data Flow Examples

### 1. Intake Chat Flow (User → Prediction)

```mermaid
sequenceDiagram
    participant User
    participant Frontend as Next.js Frontend
    participant API as FastAPI Backend
    participant IntakeService
    participant IntakeAgent
    participant Claude as Claude API
    participant Storage as File System

    User->>Frontend: Opens /chat
    Frontend->>API: POST /chat/start {role: "tenant"}
    API->>IntakeService: start_session("tenant")
    IntakeService->>IntakeAgent: start_conversation(role)
    IntakeAgent->>Claude: Generate greeting + first question
    Claude-->>IntakeAgent: Response
    IntakeAgent-->>IntakeService: Conversation state
    IntakeService->>Storage: Save session JSON
    IntakeService-->>API: Session data + greeting
    API-->>Frontend: {sessionId, response, stage, completeness}
    Frontend-->>User: Display chat interface

    loop Chat Conversation
        User->>Frontend: Sends message
        Frontend->>API: POST /chat/message {sessionId, message}
        API->>IntakeService: process_message(sessionId, message)
        IntakeService->>IntakeAgent: continue_conversation(message)
        IntakeAgent->>Claude: Extract entities + generate next question
        Claude-->>IntakeAgent: Extracted facts + response
        IntakeAgent-->>IntakeService: Updated case file + response
        IntakeService->>Storage: Update session JSON
        IntakeService-->>API: {response, completeness, isComplete}
        API-->>Frontend: Display response + progress
        Frontend-->>User: Show message + sidebar updates
    end

    IntakeService->>IntakeService: completeness >= 80%
    IntakeService->>Storage: Mark session complete
    IntakeService-->>Frontend: {isComplete: true, suggested_actions: ["generate_prediction"]}
    Frontend-->>User: Show "Generate Prediction" button
```

### 2. Prediction Generation Flow

```mermaid
sequenceDiagram
    participant User
    participant Frontend as Next.js Frontend
    participant API as FastAPI Backend
    participant PredictionService
    participant KGBuilder as Knowledge Graph
    participant RAG as RAG Pipeline
    participant Claude as Claude API
    participant Storage as File System

    User->>Frontend: Clicks "Generate Prediction"
    Frontend->>API: POST /predictions/generate {caseId}
    API->>PredictionService: generate_prediction(caseId)
    
    PredictionService->>Storage: Load case file
    Storage-->>PredictionService: Case JSON
    
    par Build Knowledge Graph
        PredictionService->>KGBuilder: build_graph(case_facts)
        KGBuilder->>KGBuilder: Extract entities + relationships
        KGBuilder->>Storage: Save KG JSON
        KGBuilder-->>PredictionService: Knowledge graph
    and Retrieve Similar Cases
        PredictionService->>RAG: retrieve_similar_cases(case_facts)
        RAG->>RAG: Hybrid search (BM25 + semantic)
        RAG->>RAG: Rerank by relevance
        RAG-->>PredictionService: Top 10 relevant cases
    end
    
    PredictionService->>Claude: Synthesize prediction with RAG + KG
    Note over Claude: Generates structured prediction:<br/>- Outcome (tenant_win/landlord_win/split)<br/>- Confidence scores<br/>- Reasoning trace with citations<br/>- Settlement ranges
    Claude-->>PredictionService: Structured prediction
    
    PredictionService->>Storage: Save prediction JSON
    PredictionService-->>API: Prediction result
    API-->>Frontend: Full prediction with reasoning
    Frontend-->>User: Display prediction page with:<br/>- Outcome & confidence<br/>- Reasoning trace<br/>- Similar cases<br/>- Settlement recommendations
```

### 3. Multi-Party Dispute Flow

```mermaid
sequenceDiagram
    participant Tenant
    participant TenantFE as Tenant's Browser
    participant API as FastAPI Backend
    participant DisputeService
    participant Storage as File System
    participant Landlord
    participant LandlordFE as Landlord's Browser

    Tenant->>TenantFE: Starts intake as "tenant"
    TenantFE->>API: POST /chat/start {role: "tenant", createDispute: true}
    API->>DisputeService: create_dispute()
    DisputeService->>Storage: Save dispute JSON
    DisputeService-->>API: {disputeId, inviteCode: "ABC123"}
    API-->>TenantFE: Session + Dispute info
    TenantFE-->>Tenant: Show invite code "ABC123"

    Tenant->>Tenant: Shares invite code with landlord
    
    Landlord->>LandlordFE: Opens app with invite code
    LandlordFE->>API: POST /disputes/validate-invite {inviteCode: "ABC123"}
    API->>DisputeService: validate_invite("ABC123")
    DisputeService->>Storage: Load dispute JSON
    DisputeService-->>API: {valid: true, expectedRole: "landlord"}
    API-->>LandlordFE: Validation success
    
    LandlordFE->>API: POST /chat/start {role: "landlord", inviteCode: "ABC123"}
    API->>DisputeService: join_dispute("ABC123", sessionId)
    DisputeService->>Storage: Update dispute with landlord session
    DisputeService-->>API: {joined: true, hasBothParties: true}
    API-->>LandlordFE: Start landlord intake
    
    Note over TenantFE,LandlordFE: Both parties complete their intakes independently
    
    TenantFE->>API: Check dispute status
    API->>DisputeService: get_dispute_status(disputeId)
    DisputeService-->>API: {bothPartiesComplete: true, readyForPrediction: true}
    API-->>TenantFE: Enable "Generate Joint Prediction"
    
    Tenant->>TenantFE: Generate prediction
    TenantFE->>API: POST /predictions/generate {caseId: disputeId}
    Note over API: Merges both parties' case files<br/>+ identifies conflicts<br/>+ weights evidence
    API-->>TenantFE: Combined prediction
    API-->>LandlordFE: Notify prediction available
```

## 🗄️ Persistence Layer (SHA-102)

SHA-102 ([PR #9](https://github.com/MSH4R1F/proposer/pull/9)) replaced all JSON-file persistence with a Postgres 16 database backed by SQLAlchemy async + Alembic.

### Schema Overview

13 tables grouped by aggregate:

| Aggregate | Tables |
|-----------|--------|
| **Sessions** | `intake_sessions` |
| **Disputes** | `disputes` |
| **Predictions** | `predictions`, `prediction_issues`, `prediction_reasoning_steps`, `prediction_citations` |
| **Knowledge Graph** | `knowledge_graphs`, `kg_nodes`, `kg_edges` |
| **Mediations** | `mediations`, `mediation_messages`, `structured_offers` |
| **Evidence** | `evidence_metadata` |

- **JSONB payload + projection columns**: each row stores the full Pydantic model dump in a JSONB column; scalar projection columns (e.g. `status`, `case_id`) are indexed separately for efficient filtering.
- **KG identity**: `kg_nodes` uses a composite `(case_id, node_id)` primary key to preserve polymorphic node identity across cases without surrogate keys.
- **Optimistic locking**: `version` columns on mutable aggregates; `lock_for_prediction_cache` issues a `SELECT … FOR UPDATE` row lock during the 3-stage prediction flow.

### Repositories + Unit of Work

```
Router → dependencies.py (Depends(get_uow)) → Service → UnitOfWork → Repository → AsyncSession → Postgres
```

- **`apps/api/src/db/uow.py`**: `UnitOfWork` is a request-scoped async context manager. It opens one `AsyncSession`, exposes all seven repos as attributes, commits on clean `__aexit__`, and rolls back on exception.
- **`apps/api/src/dependencies.py`**: `get_uow` / `get_*_service` factories wire per-request UoW into service constructors via FastAPI `Depends()`.
- **Repositories** (`apps/api/src/db/repositories/`): 7 repos — one per aggregate (the seventh, `PropositionsRepo`, was added by SHA-36 Phase 1). Each exposes `save`, `get`, `get_by_*`, `delete`, and `list_*` methods. Repos translate between Pydantic domain models and SQLAlchemy ORM rows.

### Atomic Flows

Five transactional boundaries introduced by SHA-102:

| Flow | Guarantee |
|------|-----------|
| `POST /chat/start` | Session + dispute create in one transaction |
| `PredictionService.generate_prediction` | Read-cache → external LLM work → write-with-row-lock-recheck (3-stage) |
| `MediationService.start_mediation` | Status check + record create atomic |
| `MediationService.settle` / `escalate` | State transition + message append atomic |
| `MediationService.respond_to_offer` (accept path) | Offer accept + auto-settle in one transaction |

### Migration / Cutover Scripts

All scripts live under `scripts/migrations/`:

- **`audit_json_stores.py`** — scans `data/` and reports record counts + schema drift vs. current Pydantic models.
- **`backfill_json_to_postgres.py`** — migrates existing JSON files; flags: `--dry-run`, `--commit`, `--verify`, `--archive-json`. Fail-closed on validation errors, FK orphans, duplicate IDs, and projection drift.
- **`dump_postgres_to_json.py`** — rollback insurance: exports Postgres rows back to JSON files.
- **`print_db_target.py`** — cutover preflight: prints current Alembic head and DB version.
- **`check_model_alignment.py`** — CI-enforced: asserts projection column map matches current SQLAlchemy models.

### Layered Flow (Persistence)

```mermaid
graph LR
    Router["API Router"] --> Dep["dependencies.py<br/>get_*_service / get_uow"]
    Dep --> Svc["Service<br/>(IntakeService etc.)"]
    Svc --> UoW["UnitOfWork<br/>apps/api/src/db/uow.py"]
    UoW --> Repo["Repository<br/>apps/api/src/db/repositories/"]
    Repo --> Session["AsyncSession<br/>(SQLAlchemy)"]
    Session --> PG["Postgres 16<br/>13 tables"]

    classDef box fill:#8b5cf6,stroke:#6d28d9,color:#fff
    classDef db fill:#f59e0b,stroke:#d97706,color:#fff
    class Router,Dep,Svc,UoW,Repo,Session box
    class PG db
```

### Proposition KG Substrate (SHA-36, Phase 1)

SHA-36 adds a separate **offline corpus-ingestion path** for tribunal decisions. It is not user-case state and is not read by live mediation predictions in this phase.

- **Substrate**: 4 tables — `decision_documents`, `proposition_extraction_runs`, `propositions`, `proposition_edges` — added via Alembic migration `0002_add_proposition_kg.py` (3 new enums).
- **Ingestion**: opt-in CLIs under `scripts/ingestion/` (`select_proposition_corpus`, `ingest_propositions`). Each proposition is persisted only if its `source_passage` literally appears in the decision text (substrate-layer cite-or-abstain).
- **Phase 2**: PageRank-driven retrieval will consume `proposition_id`, `issue_tags`, `entities`, `proposition_edges.edge_type`, and `document_id`. Phase 1 only ships the substrate so Phase 2 can be built without re-shaping it.

See `docs/superpowers/specs/2026-05-01-sha-36-proposition-kg.md` for the full design rationale.

---

## Key Architectural Patterns

### 1. **Separation of Concerns**
- **Frontend**: UI/UX, user interactions, client-side state
- **API Routers**: HTTP request handling, validation, response formatting
- **Services**: Business logic orchestration, session management
- **Packages**: Domain-specific logic (LLM, RAG, KG)

### 2. **Dependency Injection**
- Services use FastAPI's `Depends()` for singleton management
- Lazy loading of expensive resources (RAG pipeline)

### 3. **Async/Await Throughout**
- All API endpoints and services use `async`/`await`
- Non-blocking I/O for LLM calls, file operations
- Better resource utilization for concurrent users

### 4. **Structured Data with Pydantic**
- All API requests/responses use Pydantic models
- Type safety + automatic validation
- Consistent data contracts between frontend and backend

### 5. **Modular Package Design**
- Each package (`llm_orchestrator`, `rag_engine`, `kg_builder`) can be used independently
- Clear interfaces and minimal coupling
- Easy to test in isolation

### 6. **Cite-or-Abstain RAG Pattern**
- LLM predictions MUST cite retrieved cases
- No predictions without supporting evidence
- Transparency and legal defensibility

### 7. **Hybrid Search (BM25 + Semantic)**
- Combines keyword matching (BM25) with semantic similarity
- Better recall for legal terms + conceptual similarity
- Reranking stage for precision

### 8. **Knowledge Graph Validation**
- Constraint checking (temporal logic, evidence chains)
- Confidence scores on extracted facts
- Filters low-confidence data from predictions

## Technology Choices & Rationale

| Component | Technology | Why? |
|-----------|-----------|------|
| **Frontend** | Next.js 16 (App Router) | Server components, file-based routing, optimized bundle |
| **UI Library** | shadcn/ui + Tailwind | Modern, accessible, customizable components |
| **Backend** | FastAPI | Async support, automatic OpenAPI docs, Pydantic integration |
| **LLM** | Claude 3.5 Sonnet | Best reasoning for legal analysis, structured outputs |
| **Embeddings** | OpenAI text-embedding-3-large | High quality, 3072 dimensions, good for legal text |
| **Vector DB** | ChromaDB | Lightweight, embeddable, sufficient for 500 cases |
| **Graph DB** | JSON files (Neo4j future) | Simple for MVP, JSON is debuggable, Neo4j later for complex queries |
| **Storage** | Supabase | PostgreSQL + Auth + File storage in one, generous free tier |
| **Auth** | Supabase Auth | JWT-based, integrates with PostgreSQL RLS |

## Scaling Considerations

### Current MVP Design (500 cases, <100 users)
- ✅ ChromaDB local (fast, simple)
- ✅ JSON file storage (easy debugging)
- ✅ In-memory session caching
- ✅ Single FastAPI instance

### Future Scale (10K+ cases, 1000+ users)
- 🔄 Migrate ChromaDB to Pinecone/Weaviate (managed, distributed)
- 🔄 PostgreSQL for sessions, cases, predictions (ACID, relations)
- 🔄 Neo4j for knowledge graphs (complex queries, graph algorithms)
- 🔄 Redis for session caching (distributed, persistent)
- 🔄 Horizontal scaling with load balancer
- 🔄 Langfuse for LLM observability (cost tracking, latency, quality)

## Security & Compliance

### Data Protection
- PII redaction during RAG ingestion (hash names, addresses)
- Supabase RLS (Row-Level Security) for multi-tenancy
- HTTPS only, secure cookie handling

### Legal Safety
- All predictions include disclaimer: "This is not legal advice"
- Conditional language throughout ("likely", "similar cases suggest")
- Citation-backed claims only (no hallucination)

### Prompt Injection Defense
- Treat user input as untrusted
- System prompts enforce role boundaries
- Output validation (check citations exist)

## Development Workflow

### Local Development
```bash
# Terminal 1: Backend
cd apps/api
source ../../venv/bin/activate
python -m uvicorn src.main:app --reload --port 8000

# Terminal 2: Frontend
cd apps/web
npm run dev

# Access:
# Frontend: http://localhost:3000
# API Docs: http://localhost:8000/docs
```

### Testing Strategy
- **Unit Tests**: Individual packages (RAG, KG, LLM clients)
- **Integration Tests**: API endpoints with mocked LLM
- **Evaluation Tests**: Prediction accuracy on gold standard set
- **E2E Tests**: Full user flows (Playwright/Cypress)

## Monitoring & Observability

### Current (MVP)
- Structured logging with `structlog`
- Console output with color-coded log levels
- Manual inspection of JSON files

### Planned
- **Langfuse**: LLM call tracing, token usage, latency
- **Sentry**: Error tracking, performance monitoring
- **Posthog**: User analytics, feature usage
- **Grafana**: System metrics (CPU, memory, request rate)

---

## Learning Resources for Key Concepts

### What is RAG (Retrieval-Augmented Generation)?
RAG is a technique where we **retrieve relevant information from a knowledge base** (in our case, past tribunal decisions) **before generating a response**. Think of it like:
- You're writing an essay and you first look up relevant books/articles → that's **Retrieval**
- Then you synthesize the information into your own words → that's **Generation**
- **Why?** LLMs don't "know" specific tribunal decisions, but they're great at synthesizing information if we give them the right context.

### What is a Knowledge Graph?
A **Knowledge Graph (KG)** is a way to represent information as **nodes (entities) and edges (relationships)**:
- **Nodes**: Tenant, Landlord, Evidence (receipt), Claim (£500 for cleaning)
- **Edges**: "Receipt → Supports → Cleaning Claim", "Tenancy → Ended → 2024-01-15"
- **Why?** It helps us enforce logical consistency (e.g., "evidence dated after tenancy end can't support claim") and makes complex queries easier.

### What is Hybrid Search?
**Hybrid Search** combines two search methods:
1. **BM25 (keyword search)**: Like Ctrl+F, finds exact word matches (good for legal terms like "Section 21")
2. **Semantic Search (embeddings)**: Finds similar *meanings* even if words differ (e.g., "deposit protection" ≈ "safeguarding scheme")
- **Why?** Legal text has both precise terminology (needs exact match) and conceptual similarity (needs semantic understanding)

### What are Embeddings?
**Embeddings** are numerical representations of text (like converting words to coordinates):
- "Tenant deposit dispute" → `[0.23, -0.45, 0.67, ...]` (3072 numbers)
- Similar concepts have similar numbers (close in "semantic space")
- **Why?** Computers can't compare meanings directly, but they can compare numbers efficiently

### What is Async/Await?
**Async/await** lets our program do multiple things at once without blocking:
- **Sync (blocking)**: Make coffee → Wait → Make toast → Wait → Eat (8 minutes total)
- **Async (non-blocking)**: Start coffee → Start toast (while coffee brews) → Eat (5 minutes total)
- **Why?** LLM API calls take 2-5 seconds. With async, we can handle 10 users at once without each waiting for others.

### What is Structured Output?
**Structured Output** means the LLM returns data in a predictable format (like JSON):
```json
{
  "outcome": "tenant_win",
  "confidence": 0.85,
  "amount": 750.00
}
```
- **Why?** We can programmatically use this data (show progress bars, filter by confidence, etc.) instead of just displaying text.

---

**Questions?** Check the other docs:
- [API_DOCUMENTATION.md](./API_DOCUMENTATION.md) - Detailed API endpoint reference
- [USER_GUIDE.md](./USER_GUIDE.md) - How to use the system
- [DEBUG_LOGGING.md](./DEBUG_LOGGING.md) - Troubleshooting guide

