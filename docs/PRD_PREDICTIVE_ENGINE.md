# Product Requirements Document: Predictive Engine

**Document**: PRD – Predictive Engine  
**Product**: Proposer – AI-Powered Mediation for UK Tenancy Deposit Disputes  
**Version**: 1.0  
**Status**: Draft  
**Last Updated**: February 2026  

---

## 1. Executive Summary

### 1.1 Purpose

This PRD defines the **Predictive Engine**: the component that produces tribunal-outcome predictions for tenancy deposit disputes using **RAG** (retrieval of similar cases) and **Knowledge Graph** (structured dispute facts). It covers current behavior, success criteria, and a prioritized list of **improvements** to accuracy, calibration, transparency, and reliability.

### 1.2 Scope

**In scope**

- Prediction flow: CaseFile + KG → query building → RAG retrieval → cite-or-abstain → LLM synthesis → PredictionResult.
- Output contract: outcome, confidence, reasoning trace, citations, settlement range, issue-level predictions.
- Cite-or-abstain rule, legal-safety constraints, and integration with the rest of the agent mediation system.

**Out of scope**

- Intake agent (see PRD Agent Mediation System).
- Shadow Mediator / ZOPA (separate PRD).
- RAG pipeline internals (chunking, embeddings, index); only the **interface** used by the prediction engine (query in, results out) is in scope.

### 1.3 Success in One Sentence

The Predictive Engine delivers **cited, well-calibrated** tribunal-outcome predictions (tenant_win / landlord_win / split / uncertain) with a full reasoning trace, within latency and cost targets, and without unsupported legal claims.

---

## 2. Current State

### 2.1 Components

| Component | Location | Role |
|-----------|----------|------|
| **PredictionEngine** | `packages/llm_orchestrator/agents/prediction_agent.py` | Orchestrates query build, RAG call, cite-or-abstain, LLM synthesis, response parsing. |
| **PredictionResult / IssuePrediction / ReasoningStep / Citation** | `packages/llm_orchestrator/models/prediction.py` | Output models. |
| **Prediction prompts + JSON schema** | `packages/llm_orchestrator/prompts/prediction.py` | System/user prompts and required output shape. |
| **PredictionService** | `apps/api/src/services/prediction_service.py` | Loads case, builds KG, calls PredictionEngine, persists result. |
| **CaseFile.to_query_string()** | `packages/llm_orchestrator/models/case_file.py` | Builds RAG query from case file. |

### 2.2 End-to-End Flow

1. **Inputs**: CaseFile (from intake), KnowledgeGraph (built from CaseFile in PredictionService).
2. **Query build**: `_build_query(case_file)` → `case_file.to_query_string()` (issues, deposit protection, deposit amount, narrative snippet, evidence types).
3. **RAG**: `rag.retrieve(query, top_k=10, query_region=case_file.property.region)` → QueryResult (results, confidence, is_uncertain, uncertainty_reason).
4. **Cite-or-abstain**:
   - If no RAG or retrieval fails → continue with “No similar cases” context (LLM can still output uncertain).
   - If `rag_result.is_uncertain` or `rag_result.confidence < min_confidence` (default 0.5) → return **uncertain** PredictionResult, no LLM call.
   - If `len(rag_result.results) < min_cases_required` (default 3) → return **uncertain** PredictionResult.
5. **Synthesis**: Format precedents, case facts, KG summary → user prompt; system prompt + JSON schema → LLM (temperature 0.3, max_tokens 4096).
6. **Parse**: Extract JSON from response (handle markdown code blocks) → PredictionResult; on parse failure → fallback uncertain result with raw content in reasoning trace.
7. **Output**: PredictionResult (overall_outcome, overall_confidence, issue_predictions, reasoning_trace, citations, settlement range, uncertainties, disclaimer, etc.).

### 2.3 Cite-or-Abstain Rule

- **Intent**: No factual legal claim without retrieval-backed evidence.
- **Implementation**: Hard gate before LLM—if RAG confidence or result count is below threshold, return uncertain and do not call LLM for a “full” prediction.
- **In-prompt**: System prompt instructs “base predictions only on retrieved cases” and “cite specific cases”; no post-hoc verification of citations yet.

### 2.4 Known Gaps and Limitations

- **Query building**: Single string from CaseFile only; no explicit use of KG (e.g., issue nodes, evidence edges) to enrich or diversify the query.
- **KG in prompt**: KG is summarized (e.g., node/edge counts, consistency) but not a structured “story” of the dispute (e.g., “Evidence X supports Issue Y”).
- **Citation verification**: LLM can cite cases not in the retrieved set; no check that every citation appears in `retrieved_cases`.
- **Calibration**: No Brier score or reliability tracking; confidence values are not yet evaluated against actual outcomes.
- **Evaluation**: No gold-standard test set or automated accuracy pipeline.
- **Citation metadata**: RAG returns relevance/scores per result; these are not passed through to Citation (e.g., `similarity_score` in model is not populated from retrieval).
- **Retry / fallback**: No retry on LLM failure; parse failure yields a single fallback result.
- **Structured output**: Relies on JSON in natural-language response; no use of tool/structured-output API (e.g., Claude tools) to enforce schema.

---

## 3. Product Requirements

### 3.1 Functional Requirements

#### FR-1: Inputs and Invariants

- **Inputs**: CaseFile (required), KnowledgeGraph (optional but recommended). PredictionService must build KG before calling the engine.
- **Invariant**: PredictionEngine must not mutate CaseFile or KG; read-only.

#### FR-2: Output Contract

- **PredictionResult** must include:
  - `overall_outcome` (tenant_win | landlord_win | split | uncertain).
  - `overall_confidence` in [0, 1].
  - `outcome_summary` (short narrative).
  - `reasoning_trace` (steps with title, content, citations).
  - `issue_predictions` (per-issue outcome, confidence, reasoning, supporting_cases).
  - `retrieved_cases` (list of case references actually used).
  - `predicted_settlement_range` (low, high) when applicable.
  - `uncertainties`, `missing_information`, `assumptions_made`.
  - Legal **disclaimer** (informational only, not legal advice).

#### FR-3: Cite-or-Abstain

- If RAG is unavailable or returns is_uncertain or confidence &lt; min_confidence or result count &lt; min_cases_required → return `PredictionResult.create_uncertain(...)` with reason; do not call LLM for a full prediction.
- Configurable `min_confidence` and `min_cases_required` (defaults 0.5 and 3).

#### FR-4: Legal Safety

- All user-facing text must use conditional language (“likely”, “in similar cases”, “based on precedent”).
- Disclaimer must be present and prominent.
- No wording that constitutes legal advice (e.g., “you must”, “you should accept”).

#### FR-5: Transparency

- Every reasoning step and issue prediction that makes a factual legal claim should reference at least one citation from the retrieved set.
- Stored prediction must include `retrieved_cases` and `rag_confidence` for auditing.

### 3.2 Non-Functional Requirements

#### NFR-1: Latency

- p95 end-to-end (query + RAG + LLM + parse) &lt; 30 seconds under normal load.

#### NFR-2: Cost

- Target cost per prediction &lt; £0.50 (LLM + embeddings for retrieval if any extra calls).

#### NFR-3: Reliability

- Graceful degradation: RAG failure → optional “no similar cases” path or uncertain; LLM/parse failure → fallback uncertain result with explanation, no uncaught exception to user.

#### NFR-4: Observability

- Structured logs: prediction_starting, cite_or_abstain_triggered, prediction_generated, prediction_json_parse_error.
- Optional: Langfuse (or equivalent) trace for LLM call and token usage.

---

## 4. Improvements (Prioritized)

### 4.1 P0 – Critical (Accuracy & Correctness)

| ID | Improvement | Description | Acceptance |
|----|-------------|-------------|------------|
| **I1** | **Citation verification** | After parsing, verify every citation in reasoning_trace and issue_predictions appears in `retrieved_cases`. If not, either strip invalid citations and flag in uncertainties, or re-prompt / return uncertain. | No citation in output that is not in the retrieved set. |
| **I2** | **Evaluation framework** | Introduce a gold-standard test set (50–100 cases with known tribunal outcomes). Pipeline: load case → run prediction → compare overall_outcome and (if available) amounts to ground truth. Report accuracy (3-class), optional Brier score. | Reproducible accuracy and calibration metrics. |
| **I3** | **Structured output (tool use)** | Use LLM provider’s structured-output or tool-calling API so the model returns JSON that conforms to PREDICTION_JSON_SCHEMA, reducing parse failures and hallucinated fields. | Parse failure rate drops; schema violations caught at API level. |

### 4.2 P1 – High (Quality & Usability)

| ID | Improvement | Description | Acceptance |
|----|-------------|-------------|------------|
| **I4** | **KG-informed query building** | Build RAG query using KG structure: e.g., issue types from Issue nodes, evidence types from Evidence nodes, key dates from Event nodes. Optionally multiple sub-queries (e.g., one per issue) and merge results. | Query string or multi-query input improves retrieval relevance (measure via evaluation or retrieval metrics). |
| **I5** | **RAG scores in citations** | Pass through retrieval relevance/similarity from RAG results into Citation (e.g., `similarity_score`). Populate from the result object used in context. | Each citation in output has a similarity score when it comes from RAG. |
| **I6** | **Richer KG context in prompt** | Instead of only “KG summary” (counts, consistency), include a short structured summary: e.g., “Issues: cleaning, damage. Evidence: check-in inventory, photos. Events: move-in 2022-01, move-out 2023-06.” | LLM prompt contains explicit dispute structure from KG. |
| **I7** | **Calibration tracking** | For each prediction, log (outcome, confidence). When ground truth is available (e.g., from gold set or user-reported outcome), compute Brier score and reliability diagram. Target Brier &lt; 0.20. | Calibration metrics available in evaluation pipeline. |

### 4.3 P2 – Medium (Robustness & Performance)

| ID | Improvement | Description | Acceptance |
|----|-------------|-------------|------------|
| **I8** | **Retry and fallback** | On LLM timeout or 5xx: retry once with same prompt. On repeated failure: return uncertain result with “Service temporarily unavailable” style message. | No unhandled LLM errors; user always gets a result. |
| **I9** | **Configurable top_k and thresholds** | Expose `top_k`, `min_confidence`, `min_cases_required` via config or API so they can be tuned without code change. | Non-developers can run experiments. |
| **I10** | **Settlement range validation** | If predicted_settlement_range is present, validate low ≤ high and both within reasonable bounds (e.g., 0 to deposit_at_stake). Otherwise set to null or clamp and add to uncertainties. | No invalid or nonsensical ranges in output. |
| **I11** | **Data quality in confidence** | Reduce overall_confidence when CaseFile has “minimal” or “insufficient” data quality tier (e.g., cap or scale by tier). | Confidence reflects both RAG and input completeness. |

### 4.4 P3 – Nice to Have

| ID | Improvement | Description | Acceptance |
|----|-------------|-------------|------------|
| **I12** | **Multi-query RAG** | For cases with multiple issues, run one RAG query per issue (or per issue type), merge and deduplicate results, then synthesize. | Better coverage for multi-issue disputes. |
| **I13** | **Uncertainty reasons in result** | When cite-or-abstain triggers, include a structured `uncertainty_reason` (e.g., “low_rag_confidence”, “few_results”) for frontend to show specific messaging. | Clearer UX when prediction is uncertain. |
| **I14** | **Caching** | Cache RAG results by (query, region) for a short TTL to avoid duplicate retrieval for identical/similar requests (e.g., retries or repeated clicks). | Lower latency and cost on cache hit. |

---

## 5. Success Criteria

### 5.1 Technical

- **Accuracy**: On a held-out gold set, 3-class outcome accuracy (tenant_win / landlord_win / split) ≥ 70%.
- **Calibration**: Brier score ≤ 0.20 when compared to actual outcomes (where available).
- **Hallucination**: &lt; 2% of cited cases in predictions are not in the retrieved set (after I1).
- **Latency**: p95 prediction time &lt; 30 s.
- **Cost**: Average cost per prediction &lt; £0.50.
- **Reliability**: No uncaught exceptions; parse failure and LLM failure result in uncertain fallback.

### 5.2 Product

- Users see a clear outcome (or “uncertain” with reason), a readable reasoning trace, and citations they can verify.
- Settlement range, when present, is plausible (within deposit, low ≤ high).

### 5.3 Compliance

- No legal-advice wording in any output; disclaimer present; conditional language in summaries and reasoning.

---

## 6. Out of Scope

- Changing RAG pipeline internals (chunking, embeddings, index design); only the **usage** of RAG by the prediction engine is in scope.
- Intake agent design (see Agent Mediation System PRD).
- Shadow Mediator, ZOPA, or settlement agreement generation.
- Support for non–deposit-dispute claim types (e.g., rent arrears, eviction) in this PRD.

---

## 7. Dependencies and References

### 7.1 Code References

- **PredictionEngine**: `packages/llm_orchestrator/agents/prediction_agent.py`
- **Models**: `packages/llm_orchestrator/models/prediction.py`, `case_file.py`
- **Prompts**: `packages/llm_orchestrator/prompts/prediction.py`
- **Service**: `apps/api/src/services/prediction_service.py`
- **RAG interface**: `packages/rag_engine/pipeline.py` (`retrieve()`), QueryResult type.

### 7.2 Document References

- **PRD Agent Mediation System** (`docs/PRD_AGENT_MEDIATION_SYSTEM.md`): FR-4 Prediction Agent, NFRs, architecture.
- **PRD Agent Mediation System V2** (`docs/PRD_AGENT_MEDIATION_SYSTEM_V2.md`): Evaluation metrics, risks, hypotheses.
- **CLAUDE.md**: Cite-or-abstain, evaluation-driven development, success metrics.
- **README.md**: Evaluation section, targets (>70% accuracy, Brier &lt; 0.20, &lt;2% hallucination).
- **TODO.md**: “Implement Evaluation Framework”, “Measure outcome prediction accuracy”.

---

## 8. Open Questions

- **Gold set source**: Manually labeled cases from BAILII vs. synthetic cases vs. user-reported outcomes?
- **Structured output**: Claude tool use vs. OpenAI JSON mode vs. prompt-only with stricter parsing?
- **Multi-query RAG**: Merge strategy (union, take top per issue, or single merged ranking)?
- **Confidence scaling**: Exact formula for scaling by data quality tier (e.g., 0.8 multiplier for “minimal”, 0.5 for “insufficient”)?

---

**Document owner**: Engineering  
**Review**: Update when improvements are implemented or success criteria change.
