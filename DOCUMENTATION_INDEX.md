# Legal Mediation System - Documentation Index

This document provides a comprehensive overview of all markdown documentation files in the **legal-mediation-system** project. Use this as a guide to understand the project's structure, progress, and technical details.

---

## 📚 Table of Contents

1. [Core Documentation](#core-documentation)
2. [Development Tracking](#development-tracking)
3. [Technical Documentation](#technical-documentation)
4. [Document Usage Guide](#document-usage-guide)

---

## 📖 Core Documentation

### `README.md` (18KB, 529 lines)
**Purpose**: Main project documentation and getting started guide

**Key Sections**:
- **The Problem**: Explains the justice gap in UK tenancy deposits (70% can't afford solicitors, 12-month delays, information asymmetry)
- **Our Solution**: Outcome-driven mediation platform with glass-box reasoning, predictive analytics, and rational mediation
- **How It Works**:
  - Intelligent Intake (dynamic AI agent questions)
  - Hybrid Analysis (RAG + Knowledge Graph)
  - Transparent Prediction (reasoning traces with citations)
  - Shadow Mediation (ZOPA calculation, real-time nudges)
- **Tech Stack**:
  - Backend: FastAPI, Langfuse (observability), ChromaDB, Neo4j, Supabase
  - Frontend: Next.js 16, TypeScript, shadcn/ui, Tailwind CSS
  - AI/ML: Claude 3.5 Sonnet (primary), Claude 3.5 Haiku (fallback), text-embedding-3-small (embeddings)
- **Project Structure**: Complete directory tree with descriptions
- **Getting Started**: Installation instructions, API testing commands
- **Evaluation Metrics**: Prediction accuracy >70%, Brier Score <0.20, hallucination rate <2%, response time <30s

**Target Audience**: New developers, stakeholders, anyone wanting to understand or run the project

**Key Commands**:
```bash
# Backend
python scripts/api.py                  # Start FastAPI server

# Frontend
cd apps/web && npm run dev             # Start Next.js app

# RAG Pipeline
python scripts/rag.py query "deposit not protected"
python scripts/rag.py stats

# Testing
python scripts/run_tests.py           # Run 141 tests
```

---

### `CLAUDE.md` (11KB, 269 lines)
**Purpose**: AI assistant context and development philosophy for Claude/Cursor

**Key Sections**:
- **What You're Helping Build**: Explains Proposer is not just a chatbot but a hybrid RAG + KG system that predicts judicial outcomes
- **Why This Matters**: Mohamed's perspective as founder/researcher - thesis work, potential startup, case study
- **Core Architecture**: 
  - Flow diagram: User Input → Intake Agent → KG → RAG → Prediction → Reasoning → Shadow Mediator
  - Components: RAG Pipeline (cite-or-abstain rule), Knowledge Graph (logical consistency), Hybrid Reasoning, Shadow Mediator (ZOPA calculation)
- **What Makes This Different**: Comparison table vs Traditional Mediation vs Legal Chatbots
- **Technical Challenges**:
  1. Legal data is messy (inconsistent PDFs, need OCR, "unitization" layer)
  2. Hallucination is catastrophic (strict cite-or-abstain rule)
  3. Legal Advice vs Information (regulatory risk, conditional language)
  4. Prompt Injection & Security (treat user input as untrusted)
  5. Cost Management (tiered model strategy)
- **Development Philosophy**:
  - Evaluation-driven development (measure everything)
  - Monolith first, optimize later
  - Human-in-loop for critical decisions
- **Priority Framework**:
  1. Correctness (legal accuracy > speed)
  2. Transparency (comprehensive reasoning traces)
  3. User Experience (plain English)
  4. Security (no PII leakage)
  5. Scalability (cost-per-case allows £10-20 pricing)
- **Sprint Roadmap**: 8 weeks to MVP across 4 sprints
- **Success Metrics**: Technical (>70% accuracy), Product (50 beta users), Academic (novel contribution), Commercial (100 waitlist signups)

**Target Audience**: AI assistants (Claude, Cursor), new developers learning the codebase

**Why It Matters**: Provides context about project goals, technical constraints, and development principles that AI assistants should follow.

---

### `.cursorrules` (15KB, 371 lines)
**Purpose**: Development guidelines and coding standards for Cursor IDE

**Key Sections**:
- **Legal Safety First**: All outputs framed as information, not advice; conditional language mandatory; prominent disclaimers
- **Cite or Abstain**: Never generate claims without retrieval evidence; mark uncertainty explicitly
- **Evaluation Driven**: Every feature must have metrics; compare to baseline; track over time
- **Transparent Reasoning**: Every prediction includes reasoning trace with step-by-step logic and citations
- **Type Safety**: TypeScript on frontend (strict mode), Pydantic on backend
- **Code Organization**: Monorepo structure (apps/, packages/, data/, scripts/); dependency rules
- **Testing**: Unit tests for pure functions, integration tests for pipelines, evaluation tests for accuracy
- **Naming Conventions**: Descriptive names, avoid abbreviations, consistent patterns
- **Error Handling**: Graceful degradation, user-friendly messages, detailed logging
- **Performance**: Cost per case <£0.50, response time <30s, optimize after correctness
- **Security**:
  - Treat user input as untrusted
  - Strict prompt boundaries (no leaking system prompts)
  - PII redaction in logs
  - Rate limiting on expensive operations
- **Collaboration**: Conventional commits, thorough PR descriptions, tag reviewers for legal/eval changes

**Target Audience**: Developers using Cursor IDE, AI assistants generating code

**Why It Matters**: Ensures consistent code quality, legal compliance, and technical rigor across the codebase.

---

## 📊 Development Tracking

### `CHANGELOG.md` (29KB, 553 lines)
**Purpose**: Detailed version history of all changes, features, and fixes

**Format**: Based on [Keep a Changelog](https://keepachangelog.com/), adheres to [Semantic Versioning](https://semver.org/)

**Major Sections**:

#### [Unreleased] - Latest Changes
- **Architecture Documentation** (`docs/ARCHITECTURE.md`): Mermaid diagrams for system architecture, sequence diagrams for key flows, learning resources for beginners
- **Strict Required Field Validation**: 100% required info before predictions (was 70%), clear missing field warnings, agent proactively prompts
- **Non-Blocking Completion Banner**: Chat input always visible during intake
- **Multi-Party Prediction Button Fix**: Fixed bug where button never appeared when both parties completed
- **Critical Bug Fix**: Dispute status regression (mark_party_complete wasn't idempotent)
- **Improved Invite Code Display**: Moved to sidebar, prediction blocked until both parties complete

#### Recent Features
- **Session Creation Simplification**: Reduced from 2 API calls to 1 (role set at creation)
- **Chat Session Synchronization**: Fixed multiple session IDs, message restoration, Next.js 15 params handling
- **Frontend Redesign**: Complete CSS overhaul (DM Sans font, glass morphism, gradient backgrounds, animated stats)
- **Next.js Frontend**: 60+ files (landing page, chat interface, prediction display)
- **LLM Orchestrator Package**: Conversational intake (10 stages), prediction engine, Claude client, fact extractor
- **Knowledge Graph Builder**: 7 node types, 8 edge types, JSON storage (Neo4j-ready)
- **FastAPI Application**: Chat, evidence, predictions, cases routers
- **BM25 Index Rebuild**: Fixed corruption (84 bytes → 176 MB, 43,776 chunks)

#### Development Phases (Progress Tracking)
- ✅ Phase 2: Data Pipeline (BAILII scraper, RAG pipeline, hybrid search, PII redaction)
- ✅ Phase 4: Frontend & UX (intake chat, reasoning visualization, landing page, prediction results)
- 🔄 Phase 3: Knowledge Graph (design complete, integration in progress)
- 🔄 Phase 6: Production Readiness (141 tests for RAG, more needed)
- 🔜 Phase 5: Mediation Features (shadow mediator, ZOPA, negotiation)

**Target Audience**: Developers tracking changes, stakeholders monitoring progress, academic advisors reviewing milestones

**Key Metrics (as of latest update)**:
- 141 tests for RAG engine
- 447 cases scraped from BAILII
- 43,776 chunks indexed
- 60+ frontend components created

---

### `TODO.md` (9.0KB, 351 lines)
**Purpose**: Active task list with priorities and status tracking

**Structure**:
- **🔥 High Priority**: Critical blockers
- **📋 Medium Priority**: Important but not blocking
- **🔧 Technical Improvements**: Performance/quality enhancements
- **🎯 Knowledge Graph**: KG-specific tasks
- **🚀 LLM Orchestrator**: LLM integration tasks
- **🌐 API Layer**: Backend API tasks
- **📱 Frontend**: UI/UX tasks
- **📝 Documentation**: Doc writing tasks
- **🧪 Testing**: Test coverage tasks
- **💾 Data Management**: Data pipeline tasks
- **🔒 Legal Compliance**: Regulatory tasks

**Current Top Priorities**:
1. ✅ Reset RAG Index to adjacent cases only (2,400 vs 4,336 cases for focused results)
2. ✅ Fix BM25 Index Corruption (rebuilt from ChromaDB, 43,776 chunks)
3. ✅ Test RAG Retrieval Quality (75.3% avg confidence, 100% topic precision)

**Completed Major Tasks** (✅):
- Build PDF scraper for BAILII
- Implement RAG pipeline (embeddings, hybrid search, re-ranking)
- Create Knowledge Graph Builder package
- Build LLM Orchestrator package (intake agent, prediction engine)
- Implement FastAPI application
- Create Next.js frontend (60+ files)
- Case linking system (invite codes, multi-party disputes)
- Admin dashboard
- Comprehensive test suite (141 tests)

**Target Audience**: Developers planning work, project managers tracking progress

**Last Updated**: 2026-01-08

---

### `INTERNAL_UPDATES.md` (27KB, 806 lines)
**Purpose**: Detailed log of internal changes, fixes, and technical decisions (more verbose than CHANGELOG)

**Key Updates Documented**:

#### 2026-01-08 - Case Linking & Intake Sidebar
- **Dispute Case Linking**: `DisputeCase` model with human-readable invite codes (e.g., `BLUE-TIGER-42`)
- **New API**: `/disputes/create`, `/disputes/join`, `/disputes/validate-invite`
- **User Flow**: Tenant starts → gets invite code → shares with landlord → landlord joins → both complete intake → prediction available
- **Files**: 13 new/modified files (models, services, routers, components)

#### 2026-01-06 - Session Creation Simplification
- **Before**: 2 API calls (`POST /chat/start` → `POST /chat/set-role`)
- **After**: 1 API call with role (50% reduction, ~500ms latency saved)
- **Benefits**: Faster UX, cleaner architecture, immediate role-appropriate greeting

#### 2026-01-06 - Chat Session Synchronization
- **Fixed**: Multiple session IDs on page refresh (lastSessionIdRef not updated)
- **Fixed**: Messages not restored (backend didn't return messages in session endpoint)
- **Fixed**: Next.js 15 async params (use `use()` hook)
- **Fixed**: Role selection appearing incorrectly (check stage progression)

#### 2026-01-05 - Next.js Frontend
- **Created**: Complete frontend (60+ files)
- **Components**: Chat (9), Prediction (12), UI (11), Shared (5)
- **Pages**: Landing, Chat, Prediction Results, Admin Dashboard

#### 2026-01-05 - LLM Orchestrator & KG
- **LLM Orchestrator**: 10-stage intake, Claude client, prediction engine
- **Knowledge Graph**: 7 node types, 8 edge types, validators, JSON storage
- **FastAPI**: 6 routers, 3 services

#### 2026-01-02 - RAG Stats & Diagnostics
- **Fixed**: Stats command only sampled 100 chunks (now full scan)
- **Current Status**: 43,776 chunks, 4,336 cases, avg 10.1 chunks/case
- **Year Distribution**: 2020 (21%), 2021 (45%), 2022 (30%), 2023 (3%)
- **Embedding Model Decision**: Stick with `text-embedding-3-small` (cost-effective, 6.5x cheaper than large)

**Target Audience**: Developers understanding history, troubleshooting issues, learning technical decisions

**Why It Matters**: Provides context for "why" behind code changes, documents bugs and their root causes, explains technical trade-offs.

---

## 🔧 Technical Documentation

### Technical Documentation (Referenced in other files)

The following technical documents are mentioned in the main README but located in `docs/` subdirectory:

#### `docs/PRD_AGENT_MEDIATION_SYSTEM.md`
**Status**: ✅ **Exists**
**Purpose**: Product Requirements Document for the Agent Mediation System built on RAG and Knowledge Graph.

**Key Sections**:
- **Executive Summary**: Vision for agent-driven mediation with RAG + KG as backbone
- **Current State**: RAG pipeline and KG implementation summary; current agent usage; gaps (Shadow Mediator, unified coordinator, settlement)
- **Product Requirements**: Principles (RAG/KG backbone, agent clarity, legal safety); FRs for Intake, Prediction, Shadow Mediator, Mediation Session/Coordinator, Settlement (future); NFRs (performance, security, observability, evaluation)
- **System Architecture**: High-level flow, data dependencies, agent responsibility matrix
- **Scope and Phasing**: Phase 1 (current) → Phase 2 (mediation backbone, Shadow Mediator) → Phase 3 (mediation UX) → Phase 4 (settlement)
- **Success Criteria**: Technical, product, compliance
- **Open Questions**: RAG index strategy, ZOPA formula, nudge frequency, coordinator design

**Target Audience**: Product, engineering, and stakeholders planning the evolution from prediction-only to full agent mediation.

---

#### `docs/PRD_PREDICTIVE_ENGINE.md`
**Status**: ✅ **Exists**
**Purpose**: Product Requirements Document for the Predictive Engine (RAG + KG–based outcome prediction).

**Key Sections**:
- **Executive Summary**: Scope (prediction flow, output contract, cite-or-abstain); out of scope (intake, Shadow Mediator, RAG internals)
- **Current State**: Components (PredictionEngine, models, prompts, PredictionService); end-to-end flow; cite-or-abstain rule; known gaps (query building, KG in prompt, citation verification, calibration, evaluation)
- **Product Requirements**: FRs (inputs, output contract, cite-or-abstain, legal safety, transparency); NFRs (latency, cost, reliability, observability)
- **Improvements (Prioritized)**:
  - **P0**: Citation verification (I1), Evaluation framework (I2), Structured output / tool use (I3)
  - **P1**: KG-informed query building (I4), RAG scores in citations (I5), Richer KG context in prompt (I6), Calibration tracking (I7)
  - **P2**: Retry/fallback (I8), Configurable thresholds (I9), Settlement range validation (I10), Data quality in confidence (I11)
  - **P3**: Multi-query RAG (I12), Uncertainty reasons (I13), Caching (I14)
- **Success Criteria**: Accuracy ≥70%, Brier ≤0.20, hallucination <2%, latency, cost, reliability, compliance
- **Open Questions**: Gold set source, structured output approach, multi-query merge, confidence scaling

**Target Audience**: Engineers working on prediction accuracy, calibration, and evaluation; product for prioritization of improvements.

---

#### `docs/ARCHITECTURE.md`
**Status**: ✅ **Exists** (mentioned in CHANGELOG)
**Content** (based on CHANGELOG):
- Complete system overview with Mermaid diagrams
- Full system architecture (Frontend → Backend → Packages → External Services)
- Sequence diagrams for: Intake Chat, Prediction Generation, Multi-Party Disputes
- Technology stack overview
- API endpoints mapping
- Data flow examples
- Key architectural patterns (separation of concerns, async/await, RAG patterns)
- Learning resources for beginners (What is RAG? What is KG? What is Hybrid Search?)

#### `docs/superpowers/specs/2026-04-29-postgres-migration-design.md`
**Status**: ✅ **Exists**
**Purpose**: Design spec for SHA-102 — moving user-facing state from JSON files to Postgres. Covers schema (13 tables, 15 enums), runtime layering (UoW + repositories), transaction boundaries, backfill toolchain, rollback runbook, risks, and Definition of Done.

**Target Audience**: Engineers implementing or reviewing the Postgres migration; academic readers wanting architecture rationale.

---

#### `docs/superpowers/plans/2026-04-29-postgres-migration.md`
**Status**: ✅ **Exists** (closes once PR #9 merges)
**Purpose**: Implementation plan for SHA-102. 12 phases × ~70 TDD tasks, each with file paths, failing test code, expected output, and commit commands. Used as the working canonical reference during implementation.

**Target Audience**: Developers executing SHA-102 work; post-merge historical reference for understanding implementation sequence.

---

#### `docs/superpowers/specs/2026-05-01-sha-36-proposition-kg.md`
**Status**: ✅ **Exists** (PR #15 — Phase 1 substrate landing on `feature/sha-36-proposition-kg`)
**Purpose**: Design spec for SHA-36 Phase 1 — the proposition KG substrate. Covers schema rationale for the 4 new tables (`decision_documents`, `proposition_extraction_runs`, `propositions`, `proposition_edges`), why `paragraph_ref` is a string not an int, deterministic UUID5 design and known brittleness on near-duplicate text, prompt-injection + quote-verification controls, the Phase 2 PageRank contract (out of scope here), evaluation rubric, cost ceiling, and SOTA basis (Dense X Retrieval, HippoRAG NeurIPS 2024, GraphRAG-Bench, Stanford legal RAG hallucinations, RAGAS).

**Target Audience**: Engineers reviewing PR #15 / implementing Phase 2 PageRank retrieval; thesis readers wanting the academic justification.

---

#### `docs/superpowers/plans/2026-05-01-sha-36-proposition-kg.md`
**Status**: ✅ **Exists** (orchestrator-owned, not part of PR #15)
**Purpose**: Implementation plan for SHA-36 Phase 1. 11 tasks (preflight → domain models → Postgres schema → Alembic migration → repo + UoW → text loader + provenance → proposition extractor → edge extractor + graph validator → corpus selector → ingestion CLI → integration test → docs) with exact file paths, failing test code, and acceptance gates. Each task ends in one commit.

**Target Audience**: Developers executing SHA-36 work; post-merge historical reference for understanding the substrate-then-retrieval split.

---

#### `docs/API_DOCUMENTATION.md`
**Status**: ✅ **Exists** (mentioned in TODO.md and CHANGELOG)
**Content** (based on TODO.md):
- RAG pipeline endpoints
- Request/response formats
- Example queries
- Error handling
- Package READMEs for llm_orchestrator, kg_builder, api

#### `docs/USER_GUIDE.md`
**Status**: ✅ **Exists** (mentioned in TODO.md and CHANGELOG)
**Content** (based on TODO.md):
- How to ingest cases
- How to query the system
- Understanding confidence scores
- Interpreting results

#### Other Referenced Docs
- `docs/architecture.md` - System design
- `docs/api-spec.yaml` - OpenAPI specification
- `docs/evaluation-results.md` - Performance metrics
- Package-specific READMEs:
  - `packages/rag_engine/README.md`
  - `packages/llm_orchestrator/README.md`
  - `packages/kg_builder/README.md`
  - `apps/api/README.md`

---

## 📋 Document Usage Guide

### For Onboarding New Developers
**Read in this order:**
1. **`README.md`** - Understand what Proposer is and how to run it (30 min read)
2. **`CLAUDE.md`** - Learn the development philosophy and priorities (20 min read)
3. **`.cursorrules`** - Understand coding standards and legal constraints (20 min read)
4. **`TODO.md`** - See what needs to be done (10 min read)
5. **`CHANGELOG.md`** - Skim recent changes to understand current state (15 min read)

**Total onboarding reading**: ~1.5 hours

### For Writing Academic Reports/Thesis
**Use these documents:**
1. **Introduction**:
   - Problem statement: `README.md` → "The Problem" section
   - Value proposition: `CLAUDE.md` → "What You're Helping Build"
   - Research gap: `/docs/final-interim-plan.md` → Differentiation Table

2. **Related Work**:
   - Competitors: `README.md` → "What Makes Us Different" table
   - Academic literature: `/docs/research-papers/` (all papers)
   - Gap analysis: `/docs/geminii-analysis-on-final-plan.md`

3. **Methodology**:
   - System architecture: `docs/ARCHITECTURE.md` + `README.md` → "How It Works"
   - Data collection: `CHANGELOG.md` → "RAG Engine" section (447 cases scraped)
   - Evaluation protocol: `/docs/Evaluation Framework.md`

4. **Implementation**:
   - Tech stack: `README.md` → "Tech Stack"
   - Code statistics: `CHANGELOG.md` → feature counts (60+ components, 141 tests)
   - Development process: `INTERNAL_UPDATES.md` → technical decisions

5. **Evaluation**:
   - Metrics: `README.md` → "Evaluation" section
   - Results: `docs/evaluation-results.md` (when available)
   - Test coverage: `CHANGELOG.md` → "Comprehensive Test Suite"

6. **Discussion**:
   - Challenges faced: `INTERNAL_UPDATES.md` → bug fixes and root causes
   - Technical trade-offs: `CLAUDE.md` → "Technical Challenges"
   - Future work: `/docs/plan-after-mvp-to-improve.md`

### For Code Reviews
**Reference these documents:**
- **Legal safety checks**: `.cursorrules` → "Legal Safety First" section
- **Cite-or-abstain compliance**: `.cursorrules` → "Cite or Abstain" section
- **Testing requirements**: `.cursorrules` → "Testing" section
- **Naming conventions**: `.cursorrules` → "Naming Conventions" section

### For Feature Planning
**Check these documents:**
1. **Is it already done?** → `CHANGELOG.md` (search for feature keyword)
2. **Is it planned?** → `TODO.md` (check if already in backlog)
3. **Does it align with vision?** → `CLAUDE.md` → "Development Philosophy"
4. **Will it delay MVP?** → `README.md` → "Roadmap" (check sprint timelines)
5. **Post-MVP feature?** → `/docs/plan-after-mvp-to-improve.md`

### For Debugging Issues
**Use these documents:**
1. **When did it break?** → `CHANGELOG.md` + `INTERNAL_UPDATES.md` (find recent changes)
2. **How should it work?** → `docs/ARCHITECTURE.md` (sequence diagrams)
3. **Similar bugs?** → `INTERNAL_UPDATES.md` (search for error message)
4. **API contract?** → `docs/API_DOCUMENTATION.md`

### For Stakeholder Updates
**Create reports using:**
- **Progress summary**: `CHANGELOG.md` → "Development Phases" checkboxes
- **Key metrics**: `README.md` → "Evaluation" + `TODO.md` → completed tasks count
- **Roadmap**: `README.md` → "Roadmap" section + `TODO.md` → prioritized backlog
- **Competitive positioning**: `/docs/Competitors.md`

---

## 📊 Documentation Statistics

### File Counts by Type
- **Core Documentation**: 3 files (README, CLAUDE, .cursorrules)
- **Development Tracking**: 3 files (CHANGELOG, TODO, INTERNAL_UPDATES)
- **Technical Docs** (in docs/): 4+ files (ARCHITECTURE, API_DOCUMENTATION, USER_GUIDE, evaluation-results)
- **Package READMEs**: 4 files (rag_engine, llm_orchestrator, kg_builder, api)

**Total**: ~15 documentation files

### Documentation Health
| Category | Status | Notes |
|----------|--------|-------|
| Getting Started | 🟢 **Excellent** | Comprehensive README with clear instructions |
| Architecture | 🟢 **Excellent** | Detailed diagrams and explanations |
| Development Process | 🟢 **Excellent** | Thorough changelog and tracking |
| API Documentation | 🟢 **Good** | Exists but may need updates as API evolves |
| Testing | 🟡 **Good** | 141 tests for RAG, need expansion to other packages |
| User Guide | 🟢 **Good** | Covers basic usage |
| Evaluation | 🟡 **In Progress** | Framework defined, results pending |

### Lines of Documentation
- **README.md**: 529 lines
- **CLAUDE.md**: 269 lines
- **.cursorrules**: 371 lines
- **CHANGELOG.md**: 553 lines
- **TODO.md**: 351 lines
- **INTERNAL_UPDATES.md**: 806 lines

**Total**: ~2,879 lines of documentation in main directory

### Update Frequency
- **CHANGELOG.md**: Updated with every feature/fix
- **INTERNAL_UPDATES.md**: Updated with detailed technical changes
- **TODO.md**: Last updated 2026-01-08 (recent)
- **README.md**: Updated periodically with major changes
- **CLAUDE.md**: Stable (last updated December 2024)
- **.cursorrules**: Stable (updated as needed for policy changes)

---

## 🚀 Quick Reference Commands

### Documentation Maintenance
```bash
# Update CHANGELOG after merging PR
git log --oneline --since="1 week ago"  # See recent commits
# Add to [Unreleased] section in CHANGELOG.md

# Update TODO after completing task
# Mark task as ✅ in TODO.md, move to "Completed" section

# Add internal update for complex changes
# Create new dated section in INTERNAL_UPDATES.md
```

### Finding Information
```bash
# Find when a feature was added
grep -r "feature_name" CHANGELOG.md INTERNAL_UPDATES.md

# Check if task is already planned
grep -i "task description" TODO.md

# Find technical decision reasoning
grep -r "why we chose" INTERNAL_UPDATES.md CLAUDE.md

# Check coding standards
grep -A 5 "Legal Safety" .cursorrules
```

### Documentation Standards
- **CHANGELOG.md**: Follow Keep a Changelog format, use semantic versioning
- **TODO.md**: Use emoji priorities (🔥 🔴 🟡 🟢), update last modified date
- **INTERNAL_UPDATES.md**: Include dated sections, root cause analysis, file change tables
- **README.md**: Keep examples up-to-date with actual code
- **CLAUDE.md**: Update when project priorities or philosophy change

---

## 📌 Document Relationships

```
README.md (Entry Point)
├── Links to CHANGELOG.md (for updates)
├── References CLAUDE.md (for philosophy)
├── Points to docs/ARCHITECTURE.md (for details)
└── Mentions TODO.md (for roadmap)

CLAUDE.md (AI Context)
├── References .cursorrules (for standards)
├── Aligns with /docs/final-interim-plan.md (for vision)
└── Informs INTERNAL_UPDATES.md (technical decisions)

.cursorrules (Standards)
├── Enforced in code reviews
├── Checked by AI assistants
└── Derived from /docs/Security Architecture.md

CHANGELOG.md (History)
├── Sourced from git commits
├── Feeds into INTERNAL_UPDATES.md (detailed version)
└── Updates TODO.md (mark tasks complete)

TODO.md (Planning)
├── Informs CHANGELOG.md (upcoming features)
├── Derived from /docs/plan-after-mvp-to-improve.md (future)
└── Updated by INTERNAL_UPDATES.md (task completion)

INTERNAL_UPDATES.md (Technical Log)
├── Expands on CHANGELOG.md (detailed explanations)
├── Documents bugs for future reference
└── Explains decisions not obvious from code
```

---

## 🎯 Key Takeaways

### What Proposer Is
- **Not**: Another legal chatbot or generic mediation platform
- **Is**: Hybrid RAG + Knowledge Graph system predicting judicial outcomes to anchor negotiations
- **Goal**: Bridge the justice gap in UK tenancy deposit disputes (£500-2000 claims)

### Development Status (January 2026)
- ✅ **Complete**: RAG pipeline (447 cases, 43,776 chunks), Frontend (60+ components), Backend API, Knowledge Graph builder
- 🔄 **In Progress**: Multi-party disputes, Prediction accuracy evaluation, Cost optimization
- 🔜 **Planned**: Shadow mediator, ZOPA calculation, Settlement agreement generation

### Success Criteria
- **Technical**: >70% prediction accuracy, <2% hallucination rate, <30s response time
- **Product**: 50 beta users, 10 settlements, user satisfaction >4/5
- **Academic**: Novel RAG+KG contribution, conference paper submission
- **Commercial**: 100 waitlist signups, viral content (50k+ views)

### Critical Constraints
1. **Legal Compliance**: No unauthorized legal advice, conditional language only, prominent disclaimers
2. **Cite or Abstain**: Never generate without evidence, mark uncertainty explicitly
3. **Evaluation Driven**: Every claim must be measurable and tested
4. **Security**: Treat user input as untrusted, prevent prompt injection, protect PII

### Next Major Milestones
1. Reset RAG index to adjacent cases only (increase relevance)
2. Implement evaluation framework with gold standard test set
3. Deploy shadow mediator with ZOPA calculation
4. Conduct user studies with 10-20 real disputes
5. Publish thesis and/or conference paper

---

**This Documentation Index Last Updated**: January 2026  
**Maintained By**: Mohamed Sharif (Imperial College London)  
**For Updates**: Modify this file when adding new docs or restructuring documentation  
**Related**: See `/docs/README.md` for research papers and planning documentation

