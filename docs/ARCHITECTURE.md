# Legal Mediation System - Architecture Overview

This document provides a comprehensive overview of the Proposer platform architecture, showing how the frontend (Next.js), backend (FastAPI), and core packages (domain runtime, RAG, KG, LLM) work together.

Proposer is now domain-pluggable. The default compatibility domain is `housing.deposit.v1`, while adjacent housing and research employment domains are described by `packages/domain_core` and only become usable when routing, allowlist, retrieval namespace, and launch-gate policy allow it.

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
            MediationRouter["/mediation<br/>• POST /:id/start<br/>• GET /:id/expectation/:sid<br/>• GET /:id/messages<br/>• POST /:id/message<br/>• POST /:id/offer<br/>• POST /:id/respond<br/>• GET /:id/settlement<br/>• GET /:id/settlement/pdf"]
            EvidenceRouter["/evidence<br/>• POST /upload/:caseId<br/>• GET /:caseId<br/>• DELETE /:evidenceId"]
            CasesRouter["/cases<br/>• GET /:caseId<br/>• GET /"]
            DevRouter["/api/dev (debug)<br/>• POST /agent-smoke"]
        end
        
        subgraph Services["Service Layer"]
            DomainRuntime["DomainRuntime<br/>• Domain Specs<br/>• Stage/Mode Gates<br/>• Allowlists<br/>• Eval Artifacts"]
            IntakeService["IntakeService<br/>• Session Management<br/>• Conversation Flow<br/>• Case File Building<br/>• Postgres + UoW"]
            PredictionService["PredictionService<br/>• PredictionEngineV2 wiring<br/>• Read-cache + row lock<br/>• Postgres + UoW"]
            DisputeService["DisputeService<br/>• Dispute Creation<br/>• Invite Codes<br/>• Party Linking<br/>• Postgres + UoW"]
            MediationService["MediationService<br/>• Mediation lifecycle<br/>• ZOPA + offer state<br/>• Settlement assembly<br/>• Postgres + UoW"]
            StorageService["StorageService<br/>• File Uploads<br/>• Evidence Processing<br/>• Postgres + UoW"]
        end
    end

    %% Core Packages Layer
    subgraph Packages["📦 Core Packages (Python)"]
        subgraph LLMOrchestrator["llm_orchestrator/"]
            DomainRouter["DomainRouter<br/>• Deterministic Rules<br/>• LLM Fallback<br/>• Clarifying Questions"]
            IntakeAgent["IntakeAgent<br/>• Dynamic Questioning<br/>• Context Awareness<br/>• Completeness Tracking"]
            PromptPacks["Prompt Packs<br/>• Domain Framing<br/>• Forum Policy"]
            subgraph PredictionEngineV2["PredictionEngineV2 (5-step)"]
                IssueDecomposer["IssueDecomposer"]
                IssueRetriever["IssueRetriever<br/>(per-issue RAG)"]
                IssuePredictor["IssuePredictor"]
                CitationVerifier["CitationVerifier<br/>(cite-or-abstain)"]
                OutputAssembler["OutputAssembler"]
            end
            MediatorAgent["MediatorAgent<br/>• Shadow Mediator<br/>• ZOPA computation<br/>• Nudge generation"]
            subgraph AgentLoop["agent_loop/ (foundation)"]
                LoopTool["tool / context"]
                LoopRunner["loop / trace"]
            end
            LabelerFactory["labeler_factory<br/>• LabelerModelSpec<br/>• build_labeler_client()<br/>• provider-independent A/B"]
            ClaudeClient["ClaudeClient<br/>• Anthropic API<br/>• Structured Outputs<br/>• Error Handling"]
            FactExtractor["FactExtractor<br/>• Entity Extraction<br/>• Evidence Processing"]
        end

        subgraph DomainCore["domain_core/"]
            DomainSpecs["DomainSpec YAMLs<br/>• Forum Profiles<br/>• Retrieval Namespaces<br/>• Eval Gates"]
            Registry["Registry + Hashing<br/>• Stable Spec Hashes<br/>• Import Boundary"]
        end
        
        subgraph KGBuilder["kg_builder/"]
            GraphBuilder["GraphBuilder<br/>• Node Creation<br/>• Edge Validation<br/>• Constraint Checking"]
            KGModels["KG Models<br/>• Domain IDs<br/>• Nodes (Party, Evidence, Issue)<br/>• Edges (Supports, OccurredBefore)<br/>• Validators"]
            Ontology["Ontology Registry<br/>• Per-Domain Constraints<br/>• Cross-Domain Bridges"]
        end
        
        subgraph RAGEngine["rag_engine/"]
            RAGPipeline["RAGPipeline<br/>• Query Processing<br/>• Orchestration"]
            HybridRetriever["HybridRetriever<br/>• BM25 (keyword)<br/>• Semantic Search<br/>• Domain Filters"]
            ChromaStore["ChromaStore<br/>• Vector DB<br/>• Embeddings"]
            Reranker["Reranker<br/>• Relevance Scoring<br/>• Forum/Source Filtering"]
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
        OpenAI["OpenAI API<br/>text-embedding-3-small"]
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
    MainApp --> MediationRouter
    MainApp --> EvidenceRouter
    MainApp --> CasesRouter
    MainApp --> DevRouter
    
    ChatRouter --> IntakeService
    ChatRouter --> DisputeService
    PredictionsRouter --> PredictionService
    DisputesRouter --> DisputeService
    MediationRouter --> MediationService
    EvidenceRouter --> StorageService
    CasesRouter --> IntakeService
    DevRouter --> AgentLoop

    %% Service to Package Connections
    IntakeService --> IntakeAgent
    IntakeService --> FactExtractor
    IntakeService --> GraphBuilder
    
    PredictionService --> PredictionEngineV2
    PredictionService --> RAGPipeline
    PredictionService --> GraphBuilder
    
    MediationService --> MediatorAgent
    MediationService --> PredictionEngineV2
    
    DisputeService --> GraphBuilder

    %% LLM Orchestrator Internal Connections
    IntakeAgent --> ClaudeClient
    IssueRetriever --> RAGPipeline
    IssuePredictor --> ClaudeClient
    CitationVerifier --> RAGPipeline
    MediatorAgent --> ClaudeClient
    MediatorAgent --> RAGPipeline
    AgentLoop --> ClaudeClient
    
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
    class MainApp,ChatRouter,PredictionsRouter,DisputesRouter,MediationRouter,EvidenceRouter,CasesRouter,DevRouter,IntakeService,PredictionService,DisputeService,MediationService,StorageService backend
    class IntakeAgent,IssueDecomposer,IssueRetriever,IssuePredictor,CitationVerifier,OutputAssembler,MediatorAgent,LoopTool,LoopRunner,LabelerFactory,ClaudeClient,FactExtractor,GraphBuilder,KGModels,JSONStore,RAGPipeline,HybridRetriever,ChromaStore,Reranker,LegalChunker package
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

### 2. Prediction Generation Flow (PredictionEngineV2, 5-step)

```mermaid
sequenceDiagram
    participant User
    participant Frontend as Next.js Frontend
    participant API as FastAPI Backend
    participant PredictionService
    participant Engine as PredictionEngineV2
    participant Decomposer as IssueDecomposer
    participant Retriever as IssueRetriever
    participant Predictor as IssuePredictor
    participant Verifier as CitationVerifier
    participant Assembler as OutputAssembler
    participant Claude as Claude API
    participant RAG as RAG Pipeline
    participant DB as Postgres (UoW)

    User->>Frontend: Clicks "Generate Prediction"
    Frontend->>API: POST /predictions/generate {caseId}
    API->>PredictionService: generate_prediction(caseId)

    PredictionService->>DB: read-cache (lock_for_prediction_cache)
    alt cache hit
        DB-->>PredictionService: cached prediction
        PredictionService-->>API: cached result
    else cache miss
        PredictionService->>Engine: run(case_file, kg)
        Engine->>Decomposer: decompose case into issues
        Decomposer->>Claude: structured issue list
        Claude-->>Decomposer: [issue_1 ... issue_n]
        loop For each issue
            Engine->>Retriever: retrieve(issue)
            Retriever->>RAG: hybrid search + rerank
            RAG-->>Retriever: top-k passages w/ citations
            Engine->>Predictor: predict(issue, passages)
            Predictor->>Claude: per-issue judgement
            Claude-->>Predictor: {outcome, confidence, claims[], cites[]}
        end
        Engine->>Verifier: verify(claims, cites)
        Note over Verifier: Cite-or-abstain rule:<br/>any claim without a valid<br/>retrieval citation is dropped<br/>or marked "Uncertain"
        Verifier-->>Engine: verified claim set
        Engine->>Assembler: assemble(verified, kg)
        Assembler-->>Engine: structured Prediction
        Engine-->>PredictionService: Prediction
        PredictionService->>DB: row-lock recheck + write
    end

    PredictionService-->>API: Prediction result
    API-->>Frontend: Full prediction with reasoning
    Frontend-->>User: Outcome + per-issue confidence<br/>+ verified citations
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

### 4. Mediation Flow (Shadow Mediator)

```mermaid
sequenceDiagram
    participant Tenant
    participant Landlord
    participant API as FastAPI Backend
    participant MS as MediationService
    participant Mediator as MediatorAgent
    participant Engine as PredictionEngineV2
    participant DB as Postgres (UoW)

    Note over Tenant,Landlord: Both parties already joined the dispute<br/>and a Prediction exists in DB.

    Tenant->>API: POST /mediation/{disputeId}/start
    API->>MS: start_mediation(disputeId)
    MS->>DB: status check + record create (atomic)
    MS->>Engine: load joint Prediction
    Engine-->>MS: per-issue outcomes + ranges
    MS->>Mediator: compute_zopa(prediction, party_offers)
    Mediator-->>MS: ZOPA + opening nudges

    loop Negotiation rounds
        Tenant->>API: POST /mediation/{id}/offer
        API->>MS: record offer
        MS->>Mediator: evaluate(offer, zopa, history)
        Mediator-->>MS: nudge / counter-suggestion
        MS-->>API: nudge to tenant
        Landlord->>API: POST /mediation/{id}/respond
        API->>MS: accept | counter | reject (atomic state transition)
    end

    alt Settlement reached
        MS->>DB: settle (atomic)
        API->>API: GET /mediation/{id}/settlement/pdf
    else Escalate
        MS->>DB: escalate (atomic)
    end
```

---

## Prediction Engine V2 (5-step pipeline)

`packages/llm_orchestrator/pipeline/prediction_engine_v2.py` (orchestrator) plus five sibling modules. Each step has a single responsibility; the orchestrator threads state without overlap.

| Step | Module | Responsibility |
|---|---|---|
| 1. **IssueDecomposer** | `pipeline/issue_decomposer.py` | Splits the case file into independently-judgeable legal issues (deposit-protection-window, prescribed-information-service, cleaning/damage deduction, fair-wear-and-tear, rent-arrears offset, etc.). |
| 2. **IssueRetriever** | `pipeline/issue_retriever.py` | Per-issue RAG: queries `RAGPipeline` with issue-specific framing, applies the cross-encoder reranker, returns ranked passages with stable citation IDs. |
| 3. **IssuePredictor** | `pipeline/issue_predictor.py` | Calls Claude with the (issue, passages, KG slice) tuple; returns a structured per-issue judgement: outcome, confidence, claim list, cited passage IDs. |
| 4. **CitationVerifier** | `pipeline/citation_verifier.py` | Enforces the cite-or-abstain rule. Every claim must reference a passage that actually appeared in the retrieved set; unsupported claims are dropped or marked `Uncertain`. This is the architectural firewall against hallucination. |
| 5. **OutputAssembler** | `pipeline/output_assembler.py` | Combines verified per-issue judgements into the final `Prediction` model: overall outcome, calibrated confidence, reasoning trace, settlement range, disclaimer. |

The whole pipeline is wrapped by `PredictionService` inside the SHA-102 read-cache → external work → row-lock-recheck-write atomic flow, so two concurrent `POST /predictions/generate` calls for the same case will not both pay the LLM cost.

---

## Mediator Architecture

`packages/llm_orchestrator/agents/mediator_agent.py` is the Shadow Mediator. It does **not** do prediction itself — it consumes the latest verified `Prediction` from `PredictionEngineV2` and drives mediation around it.

- **Inputs**: joint `Prediction` (per-issue outcome, confidence, settlement range), party offers, mediation history.
- **Outputs**: ZOPA computation (low/high anchored on confidence-weighted prediction), per-round nudges, settlement assembly.
- **Coordination**: `MediationService` (atomic state transitions, see Atomic Flows table below) orchestrates the agent and the dispute lifecycle. The router surface lives at `/mediation/*` (see Routers subgraph).

---

## Agent-Loop Foundation

`packages/llm_orchestrator/agent_loop/` (4 files: `tool.py`, `context.py`, `loop.py`, `trace.py`) is the tool-calling substrate. The current production wiring is the smoke loop on `/api/dev/agent-smoke` (debug-only, gated on `config.debug`); the planned migration moves both `MediatorAgent` and `PredictionEngineV2`'s LLM-call sites onto this loop so traces, retries, and tool-use are uniform. See `docs/AGENT_LOOP_FOUNDATION.md` for the contract.

---

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

### Eval-Set Labeling Pipeline (SHA-28, Phases 1–12)

A separate **offline labeling pipeline** that produces `data/gold_standard/housing_v1.jsonl` — the gold evaluation set every thesis number is graded against. Like the Proposition-KG substrate, this is not user-case state and is not read by live mediation predictions; it lives entirely under `packages/eval/auto_label/` plus two scripts under `scripts/eval/`. Decision recorded in [`docs/eval/decision-log.md`](eval/decision-log.md) D-021. Replaces the original two-paralegal blind double-annotation flow; Codex sparring at `.sisyphus/codex/sha-tbd-llm-labeling-2026-05-02.md` (8 P1/P2 findings, all integrated before any code landed).

**Why it sits in the architecture doc**: the labeling pipeline shares core packages with the live system — `llm_orchestrator/clients/labeler_factory.py` reuses `ClaudeClient` and `OpenAIClient`, the auto-grounder reuses `eval/schema.py`'s `GoldCase` invariants, and the cite-or-abstain rule that the live `CitationVerifier` enforces at prediction time has its labeling-side counterpart in `auto_label/grounder.py:check_quote`. Same firewall, two ends.

**Pipeline shape** (see also [`docs/eval/architecture.md`](eval/architecture.md)):

```text
PDF ──► auto_label.py ──► two LabelerModelSpec clients (Anthropic + OpenAI)
                              │   parallel via asyncio.gather
                              ▼
                          partial-GoldCase JSON × 2
                              │
                              ▼  packages/eval/auto_label/grounder.py
                          ground(...) — 10 deterministic checks:
                            quote span match (canonicalize + bounded
                              span_match, never whole-document fuzzy),
                            authority + statute lookups,
                            outcome/label basis spans,
                            facts leakage scan (pre_decision_record only),
                            date + amount sanity, INV-1..INV-10,
                            real-gold append-gate audit
                              │
                              ▼
                       data/eval_artifacts/labeling/<run_id>/<case_id>.json
                       (raw outputs + prompts + every reproducibility hash)
                              │
                              ▼  scripts/eval/adjudicate.py
                          adjudicator queues:
                            • MandatoryReviewSet (every metric-critical cell, always)
                            • DisagreementSet (A/B mismatch + ungrounded + null-XOR)
                            • Audit overlay (deterministic 10% sample of agreed cells)
                              │
                              ▼  packages/eval/auto_label/append_gate.py
                          assert_real_gold_appendable(...) — refuses on
                            missing labeling_provenance, negative_kind,
                            missing target_source_id, missing manifest fields,
                            incomplete MandatoryReviewSet coverage,
                            missing/mismatched run-artifact hashes
                              │
                              ▼  on green-light only
                       data/gold_standard/housing_v1.jsonl
                       (one row per case, each carrying LabelingProvenance:
                        run_id, labeler models, source/OCR hashes,
                        prompt-template hash, canonicalizer/grounder versions,
                        audit_flip_rate, mandatory_review_flip_rate,
                        inter_model_agreement_rate, per-cell field_provenance)
```

**Key components** (all under `packages/eval/auto_label/` unless noted):

| Module | Responsibility |
|---|---|
| `canonicalize.py` | NFKC + ligature expansion + dehyphenation + whitespace collapse. `CANONICALIZER_VERSION` stamped on every row. |
| `span_match.py` | Bounded-window quote matcher. Canonical-exact + small bounded edit distance ONLY inside the labeler's claimed `(page, paragraph, char_start, char_end)` window. No whole-document fuzzy fallback — closes the prompt-injection hole. |
| `disagreement.py` | Field-path `DisagreementSet` with stable identity keys (`evidence[key].kind`, `per_issue[issue=damages].winner`) so list disagreements are not hidden inside list equality. |
| `append_gate.py` | `assert_real_gold_appendable(GoldCase, run_artifact_path)` — the single chokepoint for any write to `data/gold_standard/`. |
| `leakage_scan.py` | `facts` phrase-list scan for tribunal-finding language ("the tribunal finds", "we award", …) plus span-section check restricting `facts` source spans to `pre_decision_record`. `facts` flows into `CaseFile.tenant_narrative` at prediction time, so verdict leakage here corrupts every downstream accuracy/Brier number. |
| `lookups/` | `AuthorityLookup` + `StatuteLookup` runtime-checkable Protocols with deterministic `index_id` / `index_hash` for replay. In-memory stubs ship for tests; production swaps in BAILII / `legislation.gov.uk` indexes. |
| `grounder.py` | 10 per-field check functions + `ground(...)` orchestrator. `GROUNDER_VERSION` stamped per case. |
| `runner.py` | `run_one_case(...)` async-dispatches both labelers via `asyncio.gather`, runs grounder per output, writes per-case artifact. `RUNNER_VERSION` stamped per case. |
| `prompts/extraction.py` | Labeler system prompt + `prompt_template_hash()` (sha256 of pack version + system prompt). Source PDF text is passed as data items, never interpolated into instructions — prompt-injection hardening. |
| `llm_orchestrator/clients/labeler_factory.py` | `LabelerModelSpec` + `build_labeler_client(spec)` constructing distinct concrete clients. Does NOT delegate to `get_llm_client(LLMRole.EXTRACTION)` — the role-keyed factory cannot prove provider independence (Codex finding [4]). |
| `scripts/eval/auto_label.py` | Pre-adjudication CLI. Refuses same provider for A and B. Refuses any `--artifacts-root` under `data/gold_standard/`. |
| `scripts/eval/adjudicate.py` | Adjudication CLI (`list` / `queues` / `append`). The only path that writes to `data/gold_standard/`. Writes a row to `docs/eval/reviewer-log.md` per appended case. |

**Reporting rule**: `inter_model_agreement_rate` is recorded but is **NOT Cohen's κ** and must not be reported as one. The defensibility metrics are `mandatory_review_flip_rate`, `audit_flip_rate`, anchor-set divergence (10–20-case human-only subset labeled from scratch), and adjudication rate by field path. A combined-corpus calibration claim is blocked when anchor divergence exceeds the pre-registered threshold (Brier delta > 0.05 or systematic winner-flip).

**Adjudicator onboarding**: [`docs/eval/reviewer-guide.md`](eval/reviewer-guide.md). **Methodology chapter §4.3**: [`docs/eval/methodology.md`](eval/methodology.md). **Plan**: `docs/superpowers/plans/2026-05-02-llm-labeling-pipeline.md`.

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
| **Embeddings** | OpenAI text-embedding-3-small | 1536 dimensions; matches live ChromaDB `tribunal_cases` collection and `RAGConfig` defaults (`packages/rag_engine/config.py`) |
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
RAG is a technique where we **retrieve relevant information from a knowledge base** (in our case, domain-scoped legal sources such as tribunal decisions, ombudsman determinations, legislation, guidance, and user evidence) **before generating a response**. Think of it like:
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
- "Tenant deposit dispute" → `[0.23, -0.45, 0.67, ...]` (1536 numbers — `text-embedding-3-small`, matches the live ChromaDB collection)
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
