# Product Requirements Document: Agent Mediation System

**Document**: PRD – Agent Mediation System (RAG + Knowledge Graph–Based)  
**Product**: Proposer – AI-Powered Mediation for UK Tenancy Deposit Disputes  
**Version**: 2.0  
**Status**: Draft  
**Last Updated**: February 2026  
**Author**: Mohamed Sharif (Imperial College London)

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

### 1.4 Academic Positioning

This project constitutes a **novel contribution** to the field of AI-assisted Online Dispute Resolution (ODR):

**Hypothesis H1**: A hybrid RAG + Knowledge Graph architecture produces more accurate and better-calibrated tribunal outcome predictions than either component alone.

**Hypothesis H2**: Prediction-anchored mediation (injecting predicted tribunal outcomes into negotiation) increases settlement rates and settlement fairness compared to unassisted negotiation.

**Hypothesis H3**: A cite-or-abstain discipline reduces hallucination rates below 2% without significantly degrading prediction coverage.

**Novel contributions**:
1. Hybrid RAG+KG architecture for legal case prediction with section-aware retrieval and structured fact validation.
2. Shadow mediation model: using predicted outcomes as anchoring points in automated negotiation support (evaluative mediation via AI).
3. Glass-box reasoning traces with verifiable citations for legal AI transparency.
4. Evaluation framework comparing RAG-only, KG-only, and hybrid approaches on a domain-specific legal test set.

**Related work**: Builds on ODR research (Katsh & Rabinovich-Einy, 2017), automated negotiation theory (Jennings et al., 2001), GraphRAG (Microsoft, 2024), and legal AI systems (Westlaw Edge, Casetext CoCounsel, Harvey AI). Differs from prior work by combining prediction-anchored evaluative mediation with transparent hybrid retrieval in a domain-specific context.

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
- A black-box "AI mediator" without explainability.
- An automated negotiation system that acts on behalf of parties.

Proposer **is**:

- An **evaluative, outcome-anchored** mediation platform.
- **RAG + KG–grounded**: every material claim tied to precedent or KG facts.
- **Agent-mediated**: distinct agents for intake, prediction, and negotiation support, sharing the same RAG/KG backbone.
- **Human-in-the-loop**: all decisions and offers are made by the parties; the system informs, it does not decide.

### 2.3 Differentiation

| Dimension | Traditional Mediation | Legal Chatbots | ODR Platforms (Modria, Rechtwijzer) | **Proposer** |
|-----------|----------------------|----------------|-------------------------------------|--------------|
| Data source | Mediator experience | General legal | Rule-based + historical data | 500+ tribunal cases (RAG) + KG |
| Transparency | Opaque | Vague | Limited | **Cited cases + KG-backed reasoning** |
| Goal | Any agreement | Engagement | Dispute resolution | **Fair outcome aligned with precedent** |
| Method | Facilitative | Retrieval | Evaluative (human) | **Evaluative + predictive + agent-led** |
| Prediction | None | None | Statistical only | **Per-issue, cited, calibrated** |
| Grounding | Mediator judgment | LLM knowledge | Domain rules | **Cite-or-abstain with RAG** |

### 2.4 Competitive Landscape

| Competitor | Approach | Limitation Proposer Addresses |
|-----------|----------|-------------------------------|
| **DoNotPay** | Template-based legal automation | No prediction, no case-specific reasoning |
| **Rechtwijzer** (Netherlands, discontinued) | Rule-based ODR with human mediators | Expensive human labour; no AI prediction |
| **Harvey AI** | LLM for legal professionals | Not consumer-facing; no mediation workflow |
| **Casetext CoCounsel** | RAG for legal research | No dispute resolution or mediation; lawyer-facing |
| **Deposit Protection Schemes (DPS, TDS, MyDeposits)** | Manual adjudication/mediation | Slow, opaque, no AI assistance |

---

## 3. Current State: RAG and Knowledge Graph

### 3.1 RAG Pipeline (Implemented)

- **Hybrid retrieval**: Semantic (OpenAI `text-embedding-3-small`, 1536 dims) + BM25; RRF fusion.
- **Section-aware chunking**: Legal documents split by Background/Facts/Reasoning/Decision (500 tokens/chunk, 50 token overlap).
- **Re-ranking**: By issue type, recency, region, evidence similarity.
- **Uncertainty detection**: Flags when no similar cases found; supports cite-or-abstain.
- **Scale**: ~43k chunks, 4,336+ cases (BAILII); adjacent/deposit-focused subset planned (~2,400).
- **Storage**: ChromaDB (vectors), BM25 index (keyword).

**Relevant packages**: `packages/rag_engine/` (pipeline, hybrid_retriever, reranker, chroma_store, legal_chunker).

### 3.2 Knowledge Graph (Implemented)

- **Nodes**: Party, Property, Lease, Evidence, Event, Issue, ClaimedAmount (7 types).
- **Edges**: Evidence_Supports, Event_Before/After, Party_Claims, Claim_Relates_To, Issue_Involves, Lease_For, etc. (8 types).
- **Build**: CaseFile → GraphBuilder → KnowledgeGraph; validators (temporal, evidence chain, consistency).
- **Storage**: JSON (Neo4j-ready migration path).

**Relevant packages**: `packages/kg_builder/` (models, builders, validators, json_store).

### 3.3 Current Agent Usage of RAG and KG

- **Intake Agent** (`packages/llm_orchestrator/agents/intake_agent.py`): Conversational intake (10 stages: greeting → role → property → tenancy → deposit → issues → evidence → claims → narrative → confirmation); FactExtractor populates CaseFile; GraphBuilder builds KG from CaseFile at prediction time.
- **Prediction Engine** (`packages/llm_orchestrator/agents/prediction_agent.py`): Builds query from CaseFile → RAG retrieve (top_k=10) → cite-or-abstain check (min_confidence=0.5, min_cases_required=3) → LLM synthesis with KG + RAG context → PredictionResult with reasoning trace and citations.
- **PredictionService** (`apps/api/src/services/prediction_service.py`): Orchestrates KG build, RAG-backed prediction, persistence.
- **DisputeService** (`apps/api/src/services/dispute_service.py`): Multi-party dispute creation, invite codes, party linking.

### 3.4 Gaps for Full "Agent Mediation System"

| Gap | Severity | Description |
|-----|----------|-------------|
| **Shadow Mediator** | Critical | Not implemented: no ZOPA, nudges, or negotiation support |
| **MediationCoordinator** | Critical | No explicit state machine or session orchestration for mediation phase |
| **KG query shaping** | Medium | KG built at prediction time only; not used to refine RAG queries |
| **Settlement workflow** | Medium | No flow from prediction → offers → ZOPA → settlement agreement |
| **Privacy model** | Medium | No information barriers between parties during mediation |
| **Multi-party agent view** | Low | No role-specific nudge behaviour (landlord vs. tenant view) |
| **Evaluation framework** | Medium | Gold standard test set and evaluation pipeline not yet built |
| **Graceful degradation** | Low | No defined behaviour when RAG or LLM is unavailable |

---

## 4. Product Requirements: Agent Mediation System

### 4.1 Principles

1. **RAG and KG as backbone**: All agent outputs that make legal or factual claims must be traceable to RAG retrieval and/or KG (cite-or-abstain; no unsupported legal claims).
2. **Agent clarity**: Distinct agents with clear responsibilities (Intake, Prediction, Shadow Mediator); shared context = CaseFile + KG + RAG results.
3. **Legal safety**: Information only, not advice; conditional language; prominent disclaimers; no PII in logs.
4. **Transparency**: Reasoning traces and citations shown to users; ZOPA and nudges explained in terms of precedent and KG facts.
5. **Fairness**: The system must not systematically advantage one party. Nudges and predictions apply symmetrically.
6. **Human-in-the-loop**: All decisions and offers are made by the parties themselves; the system informs and suggests, never decides or acts on behalf of a party.

### 4.2 User Personas and Flows

#### Persona: Tenant
- Demographic: Renter in England/Wales, £500–£2,000 deposit dispute, typically no legal training.
- Goal: Recover unfairly withheld deposit with evidence of what tribunals typically decide.
- Flow: Start dispute → complete intake → share invite code → see prediction → enter mediation → exchange offers → (optionally) reach settlement.

#### Persona: Landlord
- Demographic: Private landlord or letting agent, defending deposit deductions.
- Goal: Understand legal position; settle fairly if deductions are not supported by precedent.
- Flow: Receive invite code → complete intake → see prediction → enter mediation → exchange offers → (optionally) reach settlement.

#### Persona: Observer/Advisor (Future)
- Demographic: Housing charity caseworker, paralegal, or advisor helping a party.
- Goal: Review prediction and reasoning to advise their client.
- Flow: Read-only access to prediction and reasoning trace.

### 4.3 Functional Requirements

#### FR-1: RAG as Single Source of Precedent

- All precedent-based claims in prediction and mediation nudges must be backed by RAG retrieval.
- **Cite-or-abstain rule**: if confidence or number of similar cases is below threshold, system returns "Uncertain" and explains why (no fabrication).
- Configuration: `min_confidence` (default 0.5), `min_cases_required` (default 3), both configurable per agent.
- Same principle applies to Shadow Mediator nudges: every legal/factual claim in a nudge must cite a retrieved case or KG fact.
- **Citation verification**: Each citation must reference a real case in the RAG index; post-generation validation step confirms citation existence.

#### FR-2: Knowledge Graph as Single Source of Dispute Facts

- One authoritative KG per dispute, built from CaseFile (and optionally updated if new evidence/facts are added during mediation).
- All agents that reason about "what happened" or "what evidence supports what" must use this KG (and validators) to avoid contradictions.
- KG used for:
  1. Building RAG query from structured issues/evidence/claims (query shaping).
  2. Validating consistency before prediction (temporal, evidence chain).
  3. Explaining mediation nudges ("Your claim X is supported by evidence Y in the graph").
  4. Detecting conflicting accounts between tenant and landlord (merged KG from both CaseFiles).
- **KG merge strategy**: When both parties complete intake, merge their CaseFiles into a unified KG. Flag contradictions (e.g., tenant says "no damage" vs. landlord says "significant damage") as disputed nodes. Prediction engine receives both the merged KG and the list of disputed facts.

#### FR-3: Intake Agent (Existing, Enhanced)

- **Current**: 10-stage intake, role-aware (tenant/landlord), FactExtractor → CaseFile.
- **Required for agent mediation**:
  - Keep RAG out of intake (no precedent during intake); keep KG build at prediction time.
  - Optional enhancement (post-MVP): "similar cases preview" that runs RAG in read-only mode once CaseFile has minimal structure.
  - Evidence upload integration: allow users to upload documents (photos, receipts, correspondence) during intake; metadata stored in CaseFile.
- **Acceptance**:
  - Intake completes with CaseFile sufficient for KG build and RAG query.
  - No regression to cite-or-abstain or completeness metrics.
  - All required fields populated (dispute issues mandatory; property, tenancy, deposit details recommended).

#### FR-4: Prediction Agent (Existing, Clarified)

- **Current**: Query from CaseFile → RAG retrieve → cite-or-abstain → LLM + KG + RAG context → PredictionResult with reasoning trace and citations.
- **Required enhancements**:
  - **KG-enhanced query**: Query building must incorporate KG-derived structure (issue types, evidence types, temporal facts) to improve retrieval relevance.
  - **Multi-party input**: When both parties have completed intake, prediction uses the merged KG (highlighting disputed vs. agreed facts).
  - KG must be passed to the LLM alongside RAG results; reasoning trace references "case facts" (KG) and "similar cases" (RAG).
  - Output remains structured: `PredictionResult` with outcome, confidence, issue-level predictions, citations, settlement range.
  - **Settlement range**: Must be computed as part of prediction. Formula: predicted recovery amount ± confidence-adjusted band.
- **Acceptance**:
  - Prediction accuracy and citation quality maintained or improved vs. baseline.
  - KG explicitly used in prompt and (where useful) in query.
  - Every prediction includes at least 3 unique case citations.
  - Settlement range present for all non-uncertain predictions.

#### FR-5: Shadow Mediator Agent (New)

##### 5.1 Purpose

After both parties have seen the prediction, the Shadow Mediator supports negotiation by:
- Computing **ZOPA** (Zone of Possible Agreement).
- Emitting **nudges** when party behaviour diverges from precedent-based expectations.
- Providing **settlement suggestions** grounded in RAG and KG.

##### 5.2 ZOPA Calculation

**Algorithm**:

```
Let P = predicted_recovery_amount (from PredictionResult, tenant's expected recovery)
Let C = overall_confidence (0..1)
Let D = deposit_at_stake
Let σ = confidence_band = P × (1 - C) × 0.5

ZOPA_lower = max(0, P - σ)
ZOPA_upper = min(D, P + σ)

If tenant_offer is set:
    ZOPA_lower = max(ZOPA_lower, tenant_offer)
If landlord_offer is set:
    ZOPA_upper = min(ZOPA_upper, D - landlord_offer)

suggested_settlement = (ZOPA_lower + ZOPA_upper) / 2
```

**Rationale**: The ZOPA is anchored by the predicted tribunal outcome (evaluative mediation theory; Raiffa, 1982). The confidence band widens for less certain predictions, reflecting the range of plausible outcomes. Party offers narrow the ZOPA as negotiation progresses, converging on a settlement.

- **Update cadence**: ZOPA recalculated whenever a new offer is submitted or prediction is regenerated.
- **Edge cases**:
  - If `ZOPA_lower > ZOPA_upper` → no overlap ("impasse"). Shadow Mediator emits an impasse nudge explaining why positions are irreconcilable based on precedent.
  - If prediction is `UNCERTAIN` → ZOPA uses deposit range [0, D] with a warning that precedent is insufficient.
  - If one party has not made an offer → ZOPA computed from prediction only.

##### 5.3 Nudge System

**Nudge taxonomy**:

| Type | Trigger | Example |
|------|---------|---------|
| `ANCHORING` | Party sees prediction for first time | "In similar cases, tenants typically recovered £X–£Y" |
| `REALITY_CHECK` | Offer is outside ZOPA bounds | "Your offer of £200 is below the range seen in 90% of similar cases (£600–£900)" |
| `EVIDENCE_GAP` | KG shows missing evidence for a claim | "The cleaning claim has no supporting invoice in the evidence provided" |
| `PRECEDENT_ALERT` | Specific KG fact matches a strong precedent pattern | "In cases without a check-in inventory, landlords lose the full claim in 85% of cases" |
| `CONCESSION_PROMPT` | No movement after N rounds | "Neither party has moved their position. Consider: the predicted range suggests £X would be fair to both" |
| `IMPASSE_WARNING` | ZOPA has collapsed (no overlap) | "Current positions have no overlap. Tribunal resolution may be necessary" |

**Nudge rules**:
- Every nudge must cite at least one RAG case or reference a KG fact. No unsupported nudges.
- Maximum **3 nudges per party per mediation round** (fatigue prevention).
- Cooldown: minimum 1 round gap before repeating the same nudge type to the same party.
- Nudges are **role-specific**: tenant sees tenant-relevant nudges; landlord sees landlord-relevant nudges. Neither party sees the other's nudges.
- Nudge language must use **conditional framing**: "In similar cases..." / "Based on precedent..." / "The evidence suggests...". Never imperative ("You should...").
- **Ethical constraint**: Nudges must not be manipulative. They present factual information (cited precedent, evidence gaps) to help informed decision-making, not to pressure a specific outcome.

**Nudge data model**:
```python
class NudgeType(str, Enum):
    ANCHORING = "anchoring"
    REALITY_CHECK = "reality_check"
    EVIDENCE_GAP = "evidence_gap"
    PRECEDENT_ALERT = "precedent_alert"
    CONCESSION_PROMPT = "concession_prompt"
    IMPASSE_WARNING = "impasse_warning"

class Nudge(BaseModel):
    nudge_id: str
    nudge_type: NudgeType
    target_party: PartyRole  # TENANT or LANDLORD
    message: str
    citations: List[Citation]
    kg_references: List[str]  # node/edge IDs in KG
    confidence: float
    round_number: int
    timestamp: datetime
```

##### 5.4 Inputs and Outputs

- **Inputs**: CaseFile (merged), KG, PredictionResult, current offers/positions from both parties, mediation round number.
- **Outputs**: `MediationResponse` containing:
  - ZOPA range (lower, upper, suggested settlement)
  - List of nudges (each with citation and/or KG reference)
  - Status (active, impasse, settled)
  - Round summary
- **RAG usage**: Shadow Mediator reuses the same RAG pipeline. For nudges, it may issue a refined query (e.g., narrowing to specific issue type or evidence pattern from KG).

##### 5.5 Acceptance Criteria

- [ ] ZOPA computed for all non-uncertain predictions.
- [ ] 100% of nudges have at least one RAG citation or KG reference.
- [ ] No legal advice wording in any nudge text.
- [ ] Nudge rate limiting enforced (max 3 per party per round).
- [ ] ZOPA updates correctly when new offers are submitted.
- [ ] Impasse detection works when ZOPA collapses.

#### FR-6: Mediation Session and Coordinator (New)

##### 6.1 State Machine

```
                    ┌──────────────────────────┐
                    │   DISPUTE_CREATED         │
                    │   (tenant starts intake)  │
                    └──────────┬───────────────┘
                               │ landlord joins
                    ┌──────────▼───────────────┐
                    │   BOTH_PARTIES_INTAKE     │
                    │   (both completing intake)│
                    └──────────┬───────────────┘
                               │ both complete
                    ┌──────────▼───────────────┐
                    │   PREDICTION_READY        │
                    │   (prediction can run)    │
                    └──────────┬───────────────┘
                               │ prediction generated
                    ┌──────────▼───────────────┐
                    │   PREDICTION_SHARED       │
                    │   (both see prediction)   │
                    └──────────┬───────────────┘
                               │ enter mediation
                    ┌──────────▼───────────────┐
                    │   MEDIATION_ACTIVE        │
                    │   (offers + nudges)       │◄──┐
                    └──────────┬───────────────┘   │
                               │                    │ new offer
                               │                    │ submitted
                     ┌─────────┼─────────┐         │
                     │         │         │         │
              ┌──────▼──┐  ┌──▼────┐  ┌─▼────────┘
              │ SETTLED  │  │IMPASSE│  │(loop)
              └─────────┘  └───────┘
                               │
                    ┌──────────▼───────────────┐
                    │   ESCALATED               │
                    │   (referred to tribunal)  │
                    └──────────────────────────┘
```

**Transition guards**:

| Transition | Guard Condition |
|-----------|----------------|
| `DISPUTE_CREATED → BOTH_PARTIES_INTAKE` | Landlord validates invite code and joins |
| `BOTH_PARTIES_INTAKE → PREDICTION_READY` | Both parties' intake sessions marked complete (all required fields) |
| `PREDICTION_READY → PREDICTION_SHARED` | Prediction generated successfully (not uncertain) |
| `PREDICTION_SHARED → MEDIATION_ACTIVE` | Either party clicks "Enter Mediation" |
| `MEDIATION_ACTIVE → SETTLED` | Both parties accept the same settlement amount (within £10 tolerance) |
| `MEDIATION_ACTIVE → IMPASSE` | ZOPA collapses for 3+ consecutive rounds OR party requests escalation |
| `IMPASSE → ESCALATED` | Party chooses tribunal referral |
| Any state → `ABANDONED` | No activity for 30 days |

##### 6.2 MediationSession Data Model

```python
class MediationState(str, Enum):
    DISPUTE_CREATED = "dispute_created"
    BOTH_PARTIES_INTAKE = "both_parties_intake"
    PREDICTION_READY = "prediction_ready"
    PREDICTION_SHARED = "prediction_shared"
    MEDIATION_ACTIVE = "mediation_active"
    SETTLED = "settled"
    IMPASSE = "impasse"
    ESCALATED = "escalated"
    ABANDONED = "abandoned"

class MediationSession(BaseModel):
    session_id: str
    dispute_id: str
    state: MediationState
    version: int = 0  # optimistic locking for concurrent access
    
    # Party data
    tenant_case_file: CaseFile
    landlord_case_file: Optional[CaseFile]
    merged_case_file: Optional[CaseFile]
    
    # Knowledge graph
    knowledge_graph: Optional[KnowledgeGraph]
    disputed_facts: List[str] = []  # KG node IDs where parties disagree
    
    # Prediction
    prediction: Optional[PredictionResult]
    prediction_generated_at: Optional[datetime]
    
    # Mediation
    rounds: List[MediationRound] = []
    current_round: int = 0
    max_rounds: int = 10
    
    # Offers
    tenant_current_offer: Optional[float]
    landlord_current_offer: Optional[float]
    
    # ZOPA
    zopa: Optional[ZOPAResult]
    
    # Outcome
    settlement_amount: Optional[float]
    outcome: Optional[str]  # settled, impasse, escalated, abandoned
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    mediation_started_at: Optional[datetime]
    completed_at: Optional[datetime]

class MediationRound(BaseModel):
    round_number: int
    tenant_offer: Optional[float]
    landlord_offer: Optional[float]
    nudges_tenant: List[Nudge] = []
    nudges_landlord: List[Nudge] = []
    zopa_snapshot: ZOPAResult
    timestamp: datetime

class ZOPAResult(BaseModel):
    lower: float
    upper: float
    suggested_settlement: float
    has_overlap: bool
    confidence: float
    prediction_based: bool = True  # vs. offer-adjusted
```

##### 6.3 Coordinator

A thin orchestration layer (`MediationCoordinator` service in `apps/api/src/services/`) that:
1. **Manages state transitions**: Validates guards before transitions; rejects invalid transitions with 400 error.
2. **Persists session state**: JSON files for MVP; PostgreSQL for production.
3. **Dispatches to agents**: Based on current state, calls the correct agent (Prediction or Shadow Mediator).
4. **Handles concurrency**: Optimistic locking via `version` field to prevent race conditions from simultaneous party actions.
5. **Error recovery**: If an agent call fails, coordinator retries once, then returns a degraded response with explanation.
6. **Audit logging**: Every state transition, offer, and nudge logged with timestamp, actor, session ID.

##### 6.4 Acceptance Criteria

- [ ] State machine enforces valid transitions only (invalid transitions return 400).
- [ ] MediationSession persisted and recoverable across server restarts.
- [ ] Concurrent access from both parties does not corrupt state (optimistic locking).
- [ ] All state transitions logged for audit trail.
- [ ] Abandoned session detection (30-day inactivity).

#### FR-7: Privacy Model and Information Barriers

| Data Category | Tenant Sees | Landlord Sees | System Uses |
|--------------|-------------|---------------|-------------|
| Own intake data | Yes | No | Yes |
| Other party's raw narrative | No | No | Yes (for prediction) |
| Merged KG (agreed facts) | Yes | Yes | Yes |
| Disputed facts (flagged) | Yes | Yes | Yes |
| Prediction result | Yes | Yes | Yes |
| ZOPA range | Yes | Yes | Yes |
| Own nudges | Yes | No | Yes |
| Other party's nudges | No | No (own only) | Yes |
| Own offers | Yes | After submission | Yes |
| Other party's offers | After submission | Yes | Yes |
| Evidence (own uploads) | Yes | If shared/cited | Yes |

- **Asymmetric nudges**: Each party may see different nudges based on their role and position.
- **Evidence visibility**: Evidence uploaded by one party is used for prediction but only disclosed to the other party if explicitly included in the prediction reasoning trace.

#### FR-8: Settlement Agreement Generation (Future)

- **Scope**: Post–Shadow Mediator MVP.
- Agent produces a draft settlement agreement from a template:
  - "Tenant receives £X from the deposit of £D"
  - "Landlord retains £Y for [listed deductions]"
  - "Both parties waive further claims related to this deposit"
- **Constraint**: Generic and factual; numbers and roles from CaseFile/KG/prediction. Legal disclaimer required.
- **Acceptance**: Out of scope for initial MVP; included as a dependency of "full" agent mediation.

### 4.4 Non-Functional Requirements

#### NFR-1: Performance

| Operation | Target p95 Latency | Cost Target |
|-----------|-------------------|-------------|
| Intake (per message) | < 5 s | < £0.01 |
| Prediction (full) | < 30 s | < £0.20 |
| Shadow Mediator (per round) | < 15 s | < £0.10 |
| ZOPA recalculation | < 2 s | < £0.01 |
| Full journey (intake + prediction + 3 rounds) | n/a | < £0.50 |

#### NFR-2: Security and Compliance

- **Prompt injection defence**: User input never injected into system prompts as trusted instruction. All user text wrapped in `<user_input>` tags. Input sanitisation layer strips known injection patterns.
- **PII handling**: PII redacted in logs and stored outputs. Names hashed in RAG index. Evidence files stored in Supabase with RLS.
- **Legal text**: All user-facing text uses conditional language ("in similar cases", "likely", "based on precedent"). Disclaimer on every prediction and nudge.
- **UK GDPR / DPA 2018**: Right to erasure (delete case data on request); data retention policy (auto-delete after 12 months); lawful basis = legitimate interest for dispute resolution.
- **EU AI Act**: System likely falls under "limited risk" (does not make binding legal decisions). Transparency obligations apply: users informed they interact with AI; outputs labelled as AI-generated.
- **Solicitors Regulation Authority**: System does not provide "reserved legal activities". All outputs labelled as information, not advice. Recommendation to consult a solicitor included.
- **Scope enforcement**: If a user describes a non-deposit dispute (rent arrears, evictions, disrepair), the Intake Agent must politely decline and explain the system only handles deposit disputes. No prediction or mediation for out-of-scope dispute types.

#### NFR-3: Observability

- **Langfuse** for LLM calls: token usage, latency, cost per call for Intake, Prediction, and Shadow Mediator.
- **Structured logs** (structlog) for agent decisions: `prediction_skipped_low_confidence`, `nudge_shown_landlord_offer_below_range`, `zopa_collapsed_impasse`, `state_transition`.
- **Audit trail**: Every state transition, offer submission, nudge display, and prediction generation logged with timestamp, actor, and session ID. Retained 12 months.
- **Metrics dashboard**: Active disputes, mediation success rate, average rounds to settlement, nudge effectiveness (offer movement after nudge).

#### NFR-4: Evaluation

##### Prediction Evaluation (Ablation Study)

| Metric | Target | Methodology |
|--------|--------|-------------|
| Outcome accuracy (3-class) | > 70% | Held-out gold set (50–100 manually verified cases) |
| Brier score (calibration) | < 0.20 | Reliability diagrams; compare predicted vs. actual confidence |
| Hallucination rate | < 2% | Automated citation verification against RAG index |
| RAG-only vs. KG-only vs. Hybrid | Hybrid ≥ best single | Ablation on same gold set |
| Settlement range accuracy | MAE < £100 | Compare predicted range to actual tribunal award |

##### Mediation Evaluation (Post-Launch)

| Metric | Target | Methodology |
|--------|--------|-------------|
| Settlement rate | > 50% of disputes entering mediation | Track outcome of all mediation sessions |
| Settlement fairness | Within £100 of predicted range | Compare settlement to prediction |
| Rounds to settlement | Median < 5 | Track round count for settled disputes |
| Nudge effectiveness | > 30% of nudges lead to offer movement | Compare pre/post-nudge offers |
| User satisfaction | > 4/5 on fairness + clarity | Post-session survey (Likert scale) |
| Procedural fairness | No systematic party advantage | Compare tenant vs. landlord satisfaction; check for systematic bias in predictions |

#### NFR-5: Graceful Degradation

| Failure | System Behaviour |
|---------|-----------------|
| RAG unavailable | Prediction returns "Uncertain" with explanation; intake continues normally |
| LLM unavailable | All agent calls fail gracefully; user sees "Service temporarily unavailable, please try again" |
| KG build fails | Prediction proceeds with RAG-only (reduced quality); log warning |
| Supabase down | Local file storage fallback for sessions; evidence upload disabled with user notification |
| Rate limit hit (LLM API) | Exponential backoff with 3 retries; after failure, queue request and notify user of delay |

#### NFR-6: Accessibility

- WCAG 2.1 AA compliance for all user-facing UI.
- Screen reader compatibility for prediction results, reasoning traces, and ZOPA visualisation.
- English only for MVP. Architecture supports future localisation (all user-facing strings externalisable).
- Mobile-responsive design (disputes often initiated from mobile devices).

---

## 5. System Architecture (Agent Mediation)

### 5.1 High-Level Flow

```
User (Tenant/Landlord)
    → Intake Agent (conversation → CaseFile)
    → [Both parties complete] → MediationCoordinator
        → Merge CaseFiles → Flag disputed facts
        → KG build (merged CaseFile → KnowledgeGraph)
        → Prediction Agent
            → KG-enhanced RAG query
            → RAG retrieve (top_k=10)
            → Cite-or-abstain check
            → LLM synthesize (KG + RAG context) → PredictionResult
        → [Both view prediction] → Shadow Mediator Agent
            → ZOPA from prediction + party offers
            → Nudges (RAG-backed, KG-backed, role-specific)
            → Settlement suggestion
    → (Future) Settlement agreement draft
```

### 5.2 Data Dependencies

```
Tenant CaseFile ─┐
                  ├──→ Merged CaseFile ──→ Knowledge Graph ──→ Prediction Agent
Landlord CaseFile┘                    └──→ RAG Query ──────→ RAG Pipeline ──────┘
                                                                                │
                                                             PredictionResult ◄─┘
                                                                    │
                                                              Shadow Mediator
                                                               │         │
                                                            ZOPA      Nudges
```

### 5.3 Agent Responsibility Matrix

| Agent | Reads CaseFile | Reads KG | Calls RAG | Calls LLM | Outputs |
|-------|---------------|----------|-----------|-----------|---------|
| Intake Agent | Yes (update) | No | No | Yes | CaseFile, messages |
| Prediction Engine | Yes (merged) | Yes | Yes | Yes | PredictionResult, citations |
| Shadow Mediator | Yes (merged) | Yes | Yes (refined) | Yes | ZOPA, nudges (cited), settlement suggestion |
| MediationCoordinator | Yes | Yes | No | No | State transitions, session management |

### 5.4 API Endpoints (Mediation Phase)

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| `POST` | `/mediation/{dispute_id}/enter` | Transition into mediation phase | Party |
| `GET` | `/mediation/{dispute_id}/state` | Get current state, ZOPA, nudges | Party |
| `POST` | `/mediation/{dispute_id}/offer` | Submit an offer | Party |
| `GET` | `/mediation/{dispute_id}/rounds` | Get round history | Party |
| `POST` | `/mediation/{dispute_id}/accept` | Accept settlement | Party |
| `POST` | `/mediation/{dispute_id}/escalate` | Exit mediation | Party |
| `GET` | `/mediation/{dispute_id}/nudges` | Get nudges for requesting party | Party (role-filtered) |

### 5.5 Adversarial Scenario Mitigations

| Scenario | Mitigation |
|----------|-----------|
| Fake evidence to bias prediction | Evidence flagged as "party-submitted"; prediction notes provenance; contradictions highlighted |
| Prompt injection via intake | All user input sandboxed; system prompt not exposed; input sanitisation |
| Extreme offers to manipulate ZOPA | ZOPA bounds constrained by prediction ± confidence band; extremes flagged but do not override precedent |
| Stalling (same offer repeatedly) | No-movement detection → CONCESSION_PROMPT; after max_rounds → impasse |
| Cross-party data access | API enforces party role from auth token; information barrier model (FR-7) |
| System used for non-deposit dispute | Intake Agent detects out-of-scope dispute types and declines |

---

## 6. Scope and Phasing

### 6.1 In Scope

- RAG and KG as backbone for all precedent and factual claims.
- Intake Agent (as-is or minor enhancements).
- Prediction Agent with KG and RAG query shaping.
- Shadow Mediator: ZOPA + precedent-based nudges.
- Mediation session/state/coordinator (APIs + state machine).
- Privacy model and information barriers.
- Evaluation framework: gold set, ablation study, mediation metrics.

### 6.2 Out of Scope

- Legal advice or outcome guarantees.
- Automated negotiation (agent acting on behalf of party).
- Non–deposit-dispute use cases.
- Real-time chat between parties (mediation is asynchronous offer exchange).
- Payment processing or escrow.
- Integration with deposit protection scheme APIs.

### 6.3 Phased Delivery

| Phase | Focus | Deliverable | Duration |
|-------|-------|-------------|----------|
| **1 – Foundation** | RAG, KG, Intake, Prediction, multi-party | Working prediction system | **Done** |
| **2 – Mediation Backbone** | Coordinator, state machine, Shadow Mediator, mediation APIs | Backend APIs for mediation | ~3 weeks |
| **3 – Mediation UX** | Frontend mediation view, ZOPA viz, nudge cards, offer flow | End-to-end mediation in UI | ~2 weeks |
| **4 – Evaluation & Thesis** | Gold set, ablation study, user study, metrics | Evaluation results, thesis chapter | ~3 weeks |
| **5 – Settlement & Polish** | Settlement agreement, production deploy | Production system | Future |

---

## 7. Success Criteria

### 7.1 Technical

- Prediction accuracy on held-out cases > 70%; Brier score < 0.20; hallucination rate < 2%.
- RAG+KG hybrid outperforms RAG-only and KG-only on gold set (ablation study).
- Shadow Mediator: 100% of nudges have at least one RAG citation or KG reference.
- p95 latency: prediction < 30 s; Shadow Mediator < 15 s.
- Cost per full journey < £0.50.
- Citation verification pass rate > 98%.

### 7.2 Product

- 50 beta users complete full intake.
- 10 disputes reach "mediation" phase with at least one ZOPA/nudge view.
- Settlement amounts (when settled) within ~£100 of predicted range on average.
- User satisfaction (post-session) > 4/5 on "fairness" and "clarity of explanation".

### 7.3 Academic

- Ablation study demonstrates statistically significant improvement from hybrid approach.
- Hallucination rate measurably lower with cite-or-abstain vs. baseline (no constraint).
- User study demonstrates perceived fairness of AI-assisted mediation.
- Results suitable for submission to ICAIL (International Conference on AI and Law) or CHI.

### 7.4 Compliance and Safety

- Zero production incidents of "legal advice" wording.
- All outputs reviewed for conditional language and disclaimers.
- No PII in logs or in open storage.
- Prompt injection test suite passing.
- Data deletion requests fulfilled within 72 hours.

---

## 8. Open Questions and Decisions

| Question | Options | Recommendation | Status |
|----------|---------|---------------|--------|
| **RAG index scope** | Full 4,336 cases vs. adjacent-only 2,400 | Adjacent-only for relevance; evaluate with gold set | Pending evaluation |
| **ZOPA formula** | Prediction-only vs. prediction + party offers | Start prediction-only; incorporate offers in Phase 3 | Decided: phased |
| **Nudge frequency cap** | 3 per party per round vs. unlimited | 3 per party per round (fatigue prevention) | Decided: cap at 3 |
| **Coordinator pattern** | Explicit MediationCoordinator service vs. implicit | Explicit service for clarity and testability | Decided: explicit |
| **KG storage for production** | JSON files vs. Neo4j vs. PostgreSQL JSONB | JSON for MVP; PostgreSQL JSONB for production | Pending |
| **LLM provider for Shadow Mediator** | Claude Sonnet (quality) vs. Haiku (cost) | Sonnet for accuracy; evaluate Haiku for cost savings | Pending evaluation |
| **Multi-party merge strategy** | Favour tenant vs. neutral merge | Neutral merge with explicit conflict markers | Decided: neutral |
| **Nudge A/B testing** | Build framework now vs. defer | Defer to post-MVP; track nudge-to-offer-movement correlation | Decided: defer |

---

## 9. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Hallucinated citations in nudges | Medium | High | Cite-or-abstain rule; post-generation citation verification; automated tests |
| User perceives output as legal advice | Medium | High | Mandatory disclaimers; conditional language enforcement; legal review of all templates |
| Low prediction accuracy (<70%) | Medium | High | Ablation study to identify weakest component; increase case corpus; improve reranking |
| ZOPA too narrow/wide to be useful | Medium | Medium | User testing; adjustable confidence band; fallback to prediction range only |
| One party games the system | Low | Medium | Adversarial scenario mitigations (Section 5.5); rate limiting; anomaly detection |
| RAG index too small for domain coverage | Medium | Medium | Plan to expand corpus (Housing Ombudsman decisions, DPS adjudications) |
| LLM costs exceed budget | Low | Medium | Token tracking via Langfuse; model tiering (Haiku for simple tasks, Sonnet for complex) |
| Thesis timeline overrun | Medium | High | Phased delivery; Phase 4 (eval) starts in parallel with Phase 3 (UX) |

---

## 10. References

### Internal
- **CLAUDE.md**: Project philosophy, architecture, technical challenges, sprint roadmap.
- **README.md**: How it works, tech stack, evaluation metrics.
- **docs/ARCHITECTURE.md**: System architecture, sequence diagrams (intake, prediction, multi-party).
- **DOCUMENTATION_INDEX.md**: Map of all docs.
- **TODO.md**: Current tasks.
- **packages/rag_engine/README.md**, **packages/kg_builder/README.md**, **packages/llm_orchestrator/README.md**: Package-level design.

### External / Academic
- Katsh, E. & Rabinovich-Einy, O. (2017). *Digital Justice: Technology and the Internet of Disputes*. Oxford University Press.
- Jennings, N.R. et al. (2001). "Automated Negotiation: Prospects, Methods and Challenges." *Group Decision and Negotiation*, 10(2), 199–215.
- Microsoft (2024). "GraphRAG: From Local to Global Retrieval-Augmented Generation." arXiv:2404.16130.
- Raiffa, H. (1982). *The Art and Science of Negotiation*. Harvard University Press.
- Thaler, R.H. & Sunstein, C.R. (2008). *Nudge: Improving Decisions About Health, Wealth, and Happiness*.
- Tversky, A. & Kahneman, D. (1974). "Judgment under Uncertainty: Heuristics and Biases." *Science*, 185(4157), 1124–1131.
- UK Housing Act 2004, Section 213–215.
- EU AI Act (2024), Regulation (EU) 2024/1689.
- UK Data Protection Act 2018 / UK GDPR.

---

**Document owner**: Mohamed Sharif (Product / Engineering)  
**Review cadence**: Update when phasing or scope changes.  
**Next review**: After Phase 2 completion or by March 2026.
