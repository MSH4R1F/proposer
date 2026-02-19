# Product Requirements Document: Agent Mediation System

**Document**: PRD – Agent Mediation System (RAG + Knowledge Graph–Based)  
**Product**: Proposer – AI-Powered Mediation for UK Tenancy Deposit Disputes  
**Version**: 1.0  
**Status**: Draft  
**Last Updated**: February 2026  

---

## 1. Executive Summary

### 1.1 Purpose

This PRD defines the **Agent Mediation System**: the evolution of Proposer from a prediction-focused platform into a full **agent-driven mediation** product. The system is built on the existing **RAG (Retrieval-Augmented Generation)** pipeline and **Knowledge Graph (KG)** as the backbone for legal grounding, consistency, and transparency. Agents (Intake, Prediction, Shadow Mediator) coordinate to collect facts, predict outcomes, and guide parties toward fair, precedent-anchored settlements.

### 1.2 Vision

Deliver a **glass-box, agent-based mediation experience** where:

- **RAG** supplies cited precedent from real tribunal cases for every legal claim.
- **Knowledge Graph** maintains a structured, consistent representation of the dispute (parties, evidence, issues, claims, events).
- **Agents** orchestrate intake, prediction, and negotiation support in a single coherent flow, with each agent using RAG and KG as shared sources of truth.

### 1.3 Success in One Sentence

Users (tenant and landlord) complete a single mediation journey: intake → shared prediction (with reasoning and citations) → negotiation support (ZOPA, nudges) → optional settlement, all powered by RAG retrieval and KG-validated facts.

---

## 2. Strategic Context

### 2.1 Problem Statement

- **Justice gap**: Most tenants cannot afford solicitors for £500–£2,000 deposit disputes.
- **Information asymmetry**: Landlords often have more legal knowledge and resources.
- **Mediation opacity**: Traditional mediation does not show what tribunals typically decide in similar cases.
- **Delay**: First-tier Tribunal can take ~12 months; parties need faster, fairer options.

### 2.2 Product Position

Proposer is **not**:

- A generic legal chatbot.
- A replacement for lawyers or legal advice.
- A black-box “AI mediator” without explainability.

Proposer **is**:

- An **evaluative, outcome-anchored** mediation platform.
- **RAG + KG–grounded**: every material claim tied to precedent or KG facts.
- **Agent-mediated**: distinct agents for intake, prediction, and negotiation support, sharing the same RAG/KG backbone.

### 2.3 Differentiation

| Dimension        | Traditional Mediation | Legal Chatbots | **Proposer (Agent Mediation)**      |
|-----------------|------------------------|----------------|-------------------------------------|
| Data source     | Mediator experience    | General legal  | 500+ tribunal cases (RAG) + KG      |
| Transparency    | Opaque                 | Vague          | Cited cases + KG-backed reasoning   |
| Goal            | Any agreement          | Engagement     | Fair outcome aligned with precedent |
| Method          | Facilitative           | Retrieval      | Evaluative + predictive + agent-led |

---

## 3. Current State: RAG and Knowledge Graph

### 3.1 RAG Pipeline (Implemented)

- **Hybrid retrieval**: Semantic (OpenAI embeddings) + BM25; RRF fusion.
- **Section-aware chunking**: Legal documents split by Background/Facts/Reasoning/Decision.
- **Re-ranking**: By issue type, recency, region, evidence similarity.
- **Uncertainty**: Flags when no similar cases found; supports cite-or-abstain.
- **Scale**: ~43k chunks, 4,336+ cases (BAILII); adjacent/deposit-focused subset planned (~2,400).
- **Storage**: ChromaDB (vectors), BM25 index (keyword).

**Relevant packages**: `packages/rag_engine/` (pipeline, hybrid_retriever, reranker, chroma_store, legal_chunker).

### 3.2 Knowledge Graph (Implemented)

- **Nodes**: Party, Property, Lease, Evidence, Event, Issue, ClaimedAmount.
- **Edges**: Evidence_Supports, Event_Before/After, Party_Claims, Claim_Relates_To, Issue_Involves, Lease_For, etc.
- **Build**: CaseFile → GraphBuilder → KnowledgeGraph; validators (temporal, evidence chain, consistency).
- **Storage**: JSON (Neo4j-ready).

**Relevant packages**: `packages/kg_builder/` (models, builders, validators, json_store).

### 3.3 Current Agent Usage of RAG and KG

- **Intake Agent**: Conversational intake (10 stages); FactExtractor populates CaseFile; GraphBuilder builds KG from CaseFile after intake (at prediction time).
- **Prediction Engine**: Builds query from CaseFile → RAG retrieve (top_k) → cite-or-abstain check → LLM synthesis with KG + RAG context → Reasoning trace + citations.
- **PredictionService**: Orchestrates KG build, RAG-backed prediction, persistence.

### 3.4 Gaps for Full “Agent Mediation System”

- **Shadow Mediator** not implemented: no real-time negotiation support, ZOPA, or settlement nudges.
- **KG** is built at prediction time only; not yet used for **query shaping** or **multi-turn retrieval** during intake or mediation.
- **Unified agent layer**: No explicit “mediation coordinator” or shared session state that drives which agent acts when (intake vs prediction vs mediation).
- **Settlement workflow**: No agent-driven flow from prediction → offers → ZOPA calculation → settlement agreement generation.
- **Multi-party agent view**: Both parties see the same prediction; no defined agent behavior for “landlord view” vs “tenant view” during negotiation (e.g., nudges per role).

---

## 4. Product Requirements: Agent Mediation System

### 4.1 Principles

1. **RAG and KG as backbone**: All agent outputs that make legal or factual claims must be traceable to RAG retrieval and/or KG (cite-or-abstain; no unsupported legal claims).
2. **Agent clarity**: Distinct agents with clear responsibilities (Intake, Prediction, Shadow Mediator); shared context = CaseFile + KG + RAG results.
3. **Legal safety**: Information only, not advice; conditional language; prominent disclaimers; no PII in logs.
4. **Transparency**: Reasoning traces and citations shown to users; ZOPA and nudges explained in terms of precedent and KG facts.

### 4.2 User Personas and Flows

- **Tenant**: Starts dispute, completes intake, receives prediction, (later) negotiates with landlord, sees nudges and ZOPA.
- **Landlord**: Joins via invite, completes intake, sees same prediction, (later) negotiates, sees nudges and ZOPA.
- **System (agents)**: Intake Agent → Prediction Engine (RAG + KG) → (future) Shadow Mediator for negotiation and settlement support.

### 4.3 Functional Requirements

#### FR-1: RAG as Single Source of Precedent

- All precedent-based claims in prediction and (future) mediation nudges must be backed by RAG retrieval.
- Cite-or-abstain: if confidence or number of similar cases is below threshold, system returns “Uncertain” and explains why (no fabrication).
- Configuration: min_confidence, min_cases_required (currently in PredictionEngine); same principle will apply to Shadow Mediator.

#### FR-2: Knowledge Graph as Single Source of Dispute Facts

- One authoritative KG per case, built from CaseFile (and optionally updated if new evidence/facts are added).
- All agents that reason about “what happened” or “what evidence supports what” must use this KG (and validators) to avoid contradictions (e.g., events out of order, claims without supporting evidence).
- KG used for: (1) building RAG query from structured issues/evidence/claims, (2) validating consistency before prediction, (3) (future) explaining mediation nudges (“Your claim X is supported by evidence Y in the graph”).

#### FR-3: Intake Agent (Existing, Enhanced)

- **Current**: 10-stage intake, role-aware (tenant/landlord), FactExtractor → CaseFile.
- **Required for agent mediation**:
  - Keep RAG out of intake (no precedent during intake); keep KG build at prediction time.
  - Optional enhancement: as soon as CaseFile has minimal structure (e.g., one issue type), allow “preview” or “similar cases” that runs RAG in read-only mode (no prediction), to set expectations. (Scope: post-MVP if needed.)
- **Acceptance**: Intake completes with CaseFile sufficient for KG build and RAG query; no regression to cite-or-abstain or completeness.

#### FR-4: Prediction Agent (Existing, Clarified)

- **Current**: Query from CaseFile → RAG retrieve → cite-or-abstain → LLM + KG + RAG context → PredictionResult with reasoning trace and citations.
- **Required**:
  - Query building must incorporate KG-derived structure (e.g., issue types, evidence types) to improve retrieval relevance.
  - KG must be passed to the LLM alongside RAG results; reasoning trace may reference “case facts” (KG) and “similar cases” (RAG).
  - Output remains structured (outcome, confidence, issue-level predictions, citations, settlement range if applicable).
- **Acceptance**: Prediction accuracy and citation quality maintained or improved; KG explicitly used in prompt and (where useful) in query.

#### FR-5: Shadow Mediator Agent (New)

- **Purpose**: After both parties have seen the prediction, support negotiation by:
  - Computing **ZOPA** (Zone of Possible Agreement) from predicted outcome and (optionally) party positions.
  - Emitting **nudges** when an offer is outside the precedent-based range (e.g., “In 90% of similar cases, landlord did not receive full claim when no check-in inventory existed”).
  - All nudge text must be backed by RAG (cited cases) and/or KG (evidence/claims); same cite-or-abstain discipline.
- **Inputs**: CaseFile, KG, current prediction (PredictionResult), and (when available) current offers or positions from both parties.
- **Outputs**: ZOPA range (e.g., £X–£Y), optional suggested settlement band, and a list of nudges (each with citation and/or KG reference).
- **RAG usage**: Shadow Mediator reuses same RAG pipeline (same query or refined query from CaseFile/KG) to retrieve supporting cases for nudges; no new retrieval paradigm.
- **Acceptance**: Nudges only appear when supported by retrieval or KG; ZOPA is derived from prediction and (if implemented) party inputs; no legal advice wording.

#### FR-6: Mediation Session and Coordinator (New)

- **Mediation session**: After prediction is generated, the dispute can enter a “mediation” phase: both parties can see prediction, (later) exchange offers or messages, and see Shadow Mediator outputs (ZOPA, nudges).
- **Coordinator (logical)**: A thin orchestration layer that (1) decides when to run which agent (intake vs prediction vs Shadow Mediator), (2) persists session state (CaseFile, KG, PredictionResult, mediation state), (3) exposes APIs for frontend (e.g., “get prediction”, “get ZOPA and nudges”, “submit offer”).
- **Acceptance**: Clear state machine (e.g., intake → both_complete → prediction_ready → mediation_active); APIs and data model support transition into mediation and calling Shadow Mediator.

#### FR-7: Settlement Agreement Generation (Future)

- **Scope**: Post–Shadow Mediator MVP. Agent (or dedicated component) produces a draft settlement agreement (e.g., “Tenant receives £X; Landlord retains £Y; both parties waive further claims for this deposit”).
- **Constraint**: Text must be generic and factual; numbers and roles filled from CaseFile/KG/prediction. Legal disclaimer required; not a substitute for legal review.
- **Acceptance**: Out of scope for initial agent mediation MVP; included here as a dependency of “full” agent mediation.

### 4.4 Non-Functional Requirements

#### NFR-1: Performance

- Prediction (RAG + KG + LLM): target p95 &lt; 30 s.
- Shadow Mediator (ZOPA + nudges): target p95 &lt; 15 s when reusing cached RAG result or lightweight re-query.
- Cost per full journey (intake + prediction + one mediation round): target &lt; £0.50 (model costs).

#### NFR-2: Security and Compliance

- User input never injected into system prompts as trusted instruction; prompt boundaries enforced.
- PII redaction in logs and in any stored agent outputs.
- All user-facing legal text: disclaimers, conditional language (“in similar cases”, “likely”), no guarantee of outcome.

#### NFR-3: Observability

- Langfuse (or equivalent) for LLM calls (Intake, Prediction, Shadow Mediator).
- Structured logs for agent decisions (e.g., “prediction_skipped_low_confidence”, “nudge_shown_landlord_offer_below_range”).

#### NFR-4: Evaluation

- Prediction: accuracy, calibration (e.g., Brier score), hallucination rate (citations) tracked on gold set.
- Mediation (post-launch): settlement rate, fairness (e.g., distance of settlement to predicted range), user satisfaction.

---

## 5. System Architecture (Agent Mediation)

### 5.1 High-Level Flow

```
User (Tenant/Landlord)
    → Intake Agent (conversation → CaseFile)
    → [Both parties complete] → Prediction Agent
        → KG build (CaseFile → KnowledgeGraph)
        → RAG retrieve (query from CaseFile/KG)
        → Cite-or-abstain check
        → LLM synthesize (KG + RAG context) → PredictionResult
    → [Mediation phase] → Shadow Mediator Agent
        → ZOPA from prediction (and optionally offers)
        → Nudges (RAG-backed, KG-backed)
    → (Future) Settlement agreement draft
```

### 5.2 Data Dependencies

- **CaseFile**: Source for KG and for RAG query building; updated by Intake Agent and (later) by mediation inputs (e.g., offers).
- **KnowledgeGraph**: Built from CaseFile; used by Prediction Agent and Shadow Mediator for consistency and explanation.
- **RAG**: Used by Prediction Agent and Shadow Mediator; single pipeline, shared index; query can be built from CaseFile + KG (e.g., issue types, key facts).

### 5.3 Agent Responsibility Matrix

| Agent              | Reads CaseFile | Reads KG | Calls RAG | Calls LLM | Outputs                    |
|--------------------|----------------|----------|-----------|-----------|----------------------------|
| Intake Agent       | Yes (update)   | No       | No        | Yes       | CaseFile, messages         |
| Prediction Engine | Yes            | Yes      | Yes       | Yes       | PredictionResult, citations|
| Shadow Mediator   | Yes            | Yes      | Yes       | Yes       | ZOPA, nudges (cited)      |

---

## 6. Scope and Phasing

### 6.1 In Scope for “Agent Mediation System” (This PRD)

- RAG and KG as the backbone for all precedent and factual claims.
- Intake Agent (as-is or minor enhancements).
- Prediction Agent with explicit KG and RAG usage and query shaping.
- Shadow Mediator: ZOPA calculation and precedent-based nudges (RAG + KG).
- Mediation session/state and coordinator logic (APIs + state machine).
- Frontend support: show prediction, then (when built) ZOPA and nudges in a mediation view.

### 6.2 Out of Scope (Explicit)

- Legal advice; any wording that guarantees an outcome or tells users “you must”.
- Full automated negotiation (e.g., agent sending offers on behalf of a party); human-in-the-loop only.
- Non–deposit-dispute use cases (rent arrears, evictions, etc.) for this PRD.
- Replacement of RAG or KG with a different architecture (this PRD assumes RAG + KG as given).

### 6.3 Phased Delivery

- **Phase 1 – Foundation (current)**: RAG pipeline, KG build, Intake Agent, Prediction Agent, multi-party intake and shared prediction. **Done.**
- **Phase 2 – Mediation backbone**: Mediation session state, APIs for “enter mediation” and “get ZOPA/nudges”, Shadow Mediator agent (ZOPA from prediction; nudges from RAG + KG). No settlement doc yet.
- **Phase 3 – Mediation UX**: Frontend mediation view (offers, ZOPA band, nudge list with citations); optional “submit offer” and one round of Shadow Mediator response.
- **Phase 4 – Settlement (future)**: Draft settlement agreement generation, disclaimer, and download; optional e-sign flow (separate PRD if needed).

---

## 7. Success Criteria

### 7.1 Technical

- Prediction accuracy on held-out cases &gt; 70%; Brier score &lt; 0.20; hallucination rate &lt; 2%.
- Shadow Mediator: 100% of nudges have at least one RAG citation or KG reference; no unsupported legal claims.
- p95 latency: prediction &lt; 30 s; Shadow Mediator &lt; 15 s when using cached or lightweight RAG.
- Cost per full journey (intake + prediction + one mediation) &lt; £0.50.

### 7.2 Product

- 50 beta users complete full intake; 10 disputes reach “mediation” phase with at least one ZOPA/nudge view.
- Settlement amounts (when settled) within ~£100 of predicted range on average.
- User satisfaction (post-session) &gt; 4/5 on “fairness” and “clarity of explanation”.

### 7.3 Compliance and Safety

- Zero production incidents of “legal advice” wording; all outputs reviewed for conditional language and disclaimers.
- No PII in logs or in open storage; prompt injection tests passing.

---

## 8. Open Questions and Decisions

- **RAG index**: Proceed with adjacent-cases-only index (~2,400 cases) for mediation launch?
- **ZOPA formula**: Purely from PredictionResult (e.g., predicted amount ± band) or incorporate explicit party offers when available?
- **Nudge frequency**: Cap per session (e.g., max 3 nudges per party) to avoid overload?
- **Coordinator**: Implement as explicit service (“MediationCoordinator”) in backend or keep as implicit flow in existing services + new Shadow Mediator service?

---

## 9. References

- **CLAUDE.md**: Project philosophy, architecture diagram, technical challenges, sprint roadmap.
- **README.md**: How it works, tech stack, evaluation metrics.
- **docs/ARCHITECTURE.md**: System architecture, sequence diagrams (intake, prediction, multi-party).
- **DOCUMENTATION_INDEX.md**: Map of all docs.
- **TODO.md**: Current tasks (e.g., RAG index reset, evaluation framework, Shadow Mediator).
- **packages/rag_engine/README.md**, **packages/kg_builder/README.md**, **packages/llm_orchestrator/README.md**: Package-level design and usage.

---

**Document owner**: Product / Engineering  
**Review cadence**: Update when phasing or scope changes (e.g., after Phase 2 completion).
