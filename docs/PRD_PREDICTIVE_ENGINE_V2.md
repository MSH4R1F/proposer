# Product Requirements Document: Predictive Engine V2

**Document**: PRD – Predictive Engine V2 (Enhanced Multi-Step Reasoning Pipeline)  
**Product**: Proposer – AI-Powered Mediation for UK Tenancy Deposit Disputes  
**Version**: 2.0  
**Status**: Draft  
**Last Updated**: February 2026  
**Supersedes**: PRD_PREDICTIVE_ENGINE.md (V1)

---

## 1. Executive Summary

### 1.1 Purpose

This PRD defines the **next-generation Predictive Engine** for Proposer. It transforms the current single-shot LLM prediction into a **multi-step, KG-enhanced, self-verifying pipeline** that decomposes cases by issue, retrieves targeted precedents per sub-issue, generates adversarial arguments, calibrates confidence empirically, and verifies every citation before output.

The document is structured as both a product specification and a **research contribution** — each major improvement is framed as a testable hypothesis with defined metrics, enabling rigorous ablation studies for the thesis.

### 1.2 Design Principles

1. **Cite-or-Abstain**: No factual legal claim without retrieval-backed evidence. This is non-negotiable.
2. **Glass-Box Reasoning**: Every prediction step is auditable — the user can trace from outcome → issue prediction → cited case → retrieved chunk.
3. **Calibrated Confidence**: If the system says "70% tenant wins," tenants should actually win ~70% of the time across similar predictions.
4. **Graceful Degradation**: When evidence is sparse, confidence drops and uncertainty is surfaced — never fabricate certainty.
5. **Cost Discipline**: Multi-step is more expensive. The architecture must stay within £0.30/prediction via selective routing and caching.

### 1.3 Scope

**In scope**: Everything between CaseFile input and PredictionResult output — the reasoning pipeline, retrieval strategy, KG integration, calibration, verification, and evaluation framework.

**Out of scope**: Intake agent, Shadow Mediator/ZOPA, RAG index construction (chunking, embedding), frontend rendering of predictions, settlement agreement generation.

### 1.4 Key Hypotheses (Thesis Framing)

| ID | Hypothesis | Metric | Target |
|----|-----------|--------|--------|
| **H1** | Multi-step issue decomposition improves prediction accuracy over single-shot | 3-class accuracy on gold set | +8–12% over baseline |
| **H2** | KG-shaped sub-queries improve retrieval precision over flat query strings | Precision@10 per issue | +15–20% over baseline |
| **H3** | Adversarial critique reduces hallucinated citations to near-zero | Citation precision (% valid) | >98% |
| **H4** | Post-hoc calibration (isotonic regression) produces well-calibrated probabilities | ECE < 0.05, Brier < 0.20 | vs. uncalibrated baseline |
| **H5** | Temporal decay weighting improves accuracy on recent (2023–2025) cases | Accuracy on temporal holdout | +5–10% over uniform weighting |
| **H6** | Hybrid RAG+KG outperforms RAG-only and KG-only in ablation | All metrics on gold set | Hybrid > either alone |

---

## 2. Current State Assessment

### 2.1 Architecture (V1)

```
CaseFile
  → to_query_string() [flat text dump]
  → RAG.retrieve(query, top_k=10)
  → cite-or-abstain gate
  → Single LLM call (Claude Sonnet, temp=0.3)
  → JSON parse → PredictionResult
```

### 2.2 What Works

- Cite-or-abstain gate prevents predictions when evidence is insufficient
- RAG hybrid retrieval (semantic + BM25 + RRF) is solid
- Domain reranker accounts for issue type, region, recency, evidence similarity
- Output schema (PredictionResult) is well-structured and backwards-compatible
- KG builder produces valid graphs with temporal and consistency validation

### 2.3 What Doesn't Work (Gap Analysis)

| Gap | Impact | Severity |
|-----|--------|----------|
| **Single-shot prediction** | All reasoning compressed into one LLM call. No decomposition, no self-critique. Complex multi-issue cases get monolithic treatment. | Critical |
| **Flat query building** | `to_query_string()` ignores KG structure. A case with 4 issues (cleaning, damage, deposit protection, inventory) generates one query instead of targeted sub-queries per issue. | Critical |
| **No citation verification** | LLM generates citation strings but they're never checked against `retrieved_cases`. Could reference cases not in the retrieval set. | Critical |
| **Uncalibrated confidence** | Confidence is LLM self-assessment. No empirical calibration. A "75% confident" prediction has no known reliability. | High |
| **Temporal blindness** | 2020 and 2024 cases weighted equally in retrieval and reasoning. Legislative changes (Tenant Fees Act 2019, deposit protection amendments) not modelled. | High |
| **KG as decoration** | KG summary appended to prompt as text. Not used for query shaping, constraint propagation, evidence graph traversal, or contradiction detection. | High |
| **No evaluation framework** | No gold-standard test set, no automated accuracy pipeline, no calibration tracking. Cannot measure improvement. | High |
| **No multi-party merge** | When both tenant and landlord provide evidence, no structured conflict detection or credibility weighting. | Medium |
| **No ensemble/consensus** | Single model, single pass. No disagreement signal, no robustness check. | Medium |

---

## 3. Architecture: Multi-Step Reasoning Pipeline

### 3.1 Pipeline Overview

```
                              ┌──────────────────────────────────────────┐
                              │          PREDICTIVE ENGINE V2            │
                              └──────────────────────────────────────────┘

CaseFile + KG                 Step 1              Step 2                 Step 3
    │                    ┌──────────────┐   ┌────────────────────┐  ┌──────────────────┐
    ├──────────────────► │  ISSUE       │──►│  PER-ISSUE         │─►│  PER-ISSUE       │
    │                    │  DECOMPOSER  │   │  KG-ENHANCED       │  │  PREDICTOR       │
    │                    │              │   │  RETRIEVAL         │  │  (LLM + context) │
    │                    │  Identify    │   │                    │  │                  │
    │                    │  disputed    │   │  Sub-query per     │  │  Predict outcome │
    │                    │  issues,     │   │  issue from KG     │  │  per issue with  │
    │                    │  extract     │   │  nodes. Temporal   │  │  cited reasoning │
    │                    │  per-issue   │   │  decay. Evidence   │  │                  │
    │                    │  context     │   │  weighting.        │  │                  │
    │                    └──────────────┘   └────────────────────┘  └──────────────────┘
    │                                                                       │
    │                                                                       ▼
    │                     Step 6              Step 5                 Step 4
    │                ┌──────────────┐   ┌────────────────────┐  ┌──────────────────┐
    │                │  CALIBRATOR  │◄──│  CITATION          │◄─│  AGGREGATOR      │
    │                │              │   │  VERIFIER &        │  │  & CRITIC        │
    │                │  Isotonic    │   │  CRITIC            │  │                  │
    │                │  regression  │   │                    │  │  Combine per-    │
    │                │  on raw      │   │  Verify citations  │  │  issue into      │
    │                │  confidence  │   │  against RAG index │  │  overall. Run    │
    │                │  → calibrated│   │  Check KG logical  │  │  adversarial     │
    │                │  probability │   │  consistency.      │  │  critique.       │
    │                │              │   │  Flag gaps.        │  │  Detect conflicts│
    │                └──────┬───────┘   └────────────────────┘  └──────────────────┘
    │                       │
    │                       ▼
    │                ┌──────────────┐
    └───────────────►│  OUTPUT      │──► PredictionResult (backwards-compatible)
                     │  ASSEMBLER   │
                     │              │
                     │  Format,     │
                     │  disclaimer, │
                     │  settlement  │
                     │  range       │
                     └──────────────┘
```

### 3.2 Step 1: Issue Decomposer

**Purpose**: Break a complex case into discrete disputed issues, each with its own evidence and claim context.

**Approach**: Inspired by the ADAPT framework (Ask-Discriminate-Predict, EMNLP 2024) and Chain of Logic (ACL 2024) which decompose legal reasoning into independent threads.

**Input**: CaseFile, KnowledgeGraph

**Process**:
1. Extract `Issue` nodes from KG (cleaning, damage, rent_arrears, redecoration, deposit_protection, inventory, etc.)
2. For each issue, extract from KG:
   - Relevant `Evidence` nodes (linked via `Evidence_Supports` edges)
   - Relevant `ClaimedAmount` nodes
   - Relevant `Event` nodes (for timeline context)
   - `Party_Claims` from both tenant and landlord
3. If no KG available, fall back to extracting issues from `CaseFile.disputed_issues` + `tenant_claims` + `landlord_claims`
4. Produce a list of `IssueContext` objects

**Output**: `List[IssueContext]`

```python
class IssueContext(BaseModel):
    """Context for a single disputed issue, extracted from KG + CaseFile."""
    issue_type: IssueType  # enum: cleaning, damage, rent_arrears, redecoration,
                           #        deposit_protection, inventory, other
    issue_description: str
    tenant_claim: Optional[ClaimDetail]     # what tenant says + amount
    landlord_claim: Optional[ClaimDetail]   # what landlord says + amount
    supporting_evidence: List[EvidenceItem] # photos, invoices, correspondence
    timeline_events: List[TimelineEvent]    # relevant dated events
    kg_constraints: List[str]               # e.g., "no check-in inventory exists",
                                            #        "deposit not protected within 30 days"
    evidence_conflicts: List[EvidenceConflict]  # where tenant and landlord evidence disagree
    claimed_amount: Optional[float]
    data_completeness: float  # 0-1, how much evidence exists for this issue
```

**Cost**: Deterministic extraction from KG — no LLM call. ~0ms added latency.

**Fallback**: If KG is empty/unavailable, use a lightweight LLM call (Haiku-class) to identify issues from CaseFile text. Budget: ~£0.005.

---

### 3.3 Step 2: KG-Enhanced Per-Issue Retrieval

**Purpose**: Build targeted RAG queries per issue using KG structure, replacing the flat `to_query_string()`.

**Approach**: Informed by Ontology-Driven Graph RAG (2025) and the Precedent-Aware RAG Framework (2025), which showed 15–30% retrieval precision improvement by incorporating legal ontology and temporal versioning.

**Input**: `List[IssueContext]`, RAG pipeline

**Process** (per issue):

1. **Build sub-query from KG nodes**:
   ```python
   def build_issue_query(issue: IssueContext, case: CaseFile) -> str:
       """Construct a targeted query for this specific issue."""
       parts = [
           f"Tenancy deposit dispute: {issue.issue_type.value}",
           f"Deposit amount: £{case.tenancy.deposit_amount}",
           f"Tenancy duration: {case.tenancy.duration_description}",
       ]
       if issue.supporting_evidence:
           evidence_types = [e.evidence_type for e in issue.supporting_evidence]
           parts.append(f"Evidence available: {', '.join(evidence_types)}")
       if issue.kg_constraints:
           parts.append(f"Key facts: {'; '.join(issue.kg_constraints)}")
       if issue.tenant_claim:
           parts.append(f"Tenant claims: {issue.tenant_claim.description}")
       if issue.landlord_claim:
           parts.append(f"Landlord claims: {issue.landlord_claim.description}")
       return " | ".join(parts)
   ```

2. **Retrieve with temporal decay**:
   ```python
   def temporal_decay_score(case_year: int, half_life: float = 3.0) -> float:
       """Exponential decay: 50% relevance loss every half_life years."""
       age = 2026 - case_year
       return 0.5 ** (age / half_life)
   
   def retrieve_for_issue(query: str, region: str, issue_type: str) -> List[RetrievalResult]:
       raw_results = rag.retrieve(query, top_k=15, query_region=region)
       for result in raw_results:
           temporal = temporal_decay_score(result.case_year)
           issue_match = 1.2 if result.issue_type == issue_type else 1.0
           result.final_score = (
               0.55 * result.semantic_score +
               0.20 * result.bm25_score +
               0.15 * temporal +
               0.10 * issue_match
           )
       return sorted(raw_results, key=lambda r: r.final_score, reverse=True)[:10]
   ```

3. **Legislative change detection**: For issues involving deposit protection, check if case predates Tenant Fees Act 2019 or Deregulation Act 2015 changes. Tag retrieved cases with applicable legislative regime.

4. **Merge and deduplicate**: If the same case appears in multiple issue retrievals, keep it once with the highest score but annotate which issues it's relevant to.

**Output**: `Dict[IssueType, IssueRetrievalResult]`

```python
class IssueRetrievalResult(BaseModel):
    """Retrieval results targeted for a specific issue."""
    issue_type: IssueType
    query_used: str
    results: List[RetrievalResult]
    rag_confidence: float                   # from RAG pipeline
    temporal_distribution: Dict[int, int]   # year → count of retrieved cases
    legislative_regime: str                 # e.g., "post_tenant_fees_act_2019"
    is_sufficient: bool                     # >= min_cases_required for this issue
```

**Cost**: N parallel RAG calls where N = number of issues (typically 2–5). Each RAG call is ~200ms + embedding cost ~£0.001. Total: ~£0.005, ~1s (parallel).

**Fallback**: If per-issue retrieval returns < `min_cases_required` for any issue, fall back to a combined query for that issue. If still insufficient, mark issue as `uncertain`.

> **Phase 2 alternative — proposition-grained retrieval (SHA-36).** A parallel retrieval mode operating on atomic propositions (Dense X / HippoRAG style) is being built as a **substrate first**, retrieval second. The substrate (proposition extraction, typed edges, quote-verified provenance, Postgres persistence) ships in PR #15; the PageRank-over-KG retrieval that consumes it is Phase 2 and will appear in §7.3 as a new ablation row alongside `RAG-only` / `KG-only`. See [`docs/superpowers/specs/2026-05-01-sha-36-proposition-kg.md`](superpowers/specs/2026-05-01-sha-36-proposition-kg.md) for the schema and Phase 2 contract.

---

### 3.4 Step 3: Per-Issue Predictor

**Purpose**: Generate a prediction for each disputed issue independently, with cited reasoning.

**Approach**: Inspired by Chain of Logic (ACL 2024) IRAC decomposition and CourtReasoner (EMNLP 2025) which demonstrated goal-oriented legal reasoning with adversarial argument construction.

**Input**: `IssueContext`, `IssueRetrievalResult`

**Process** (per issue, parallelised):

1. **Cite-or-abstain gate** (per issue): If `issue_retrieval.is_sufficient == False`, return `IssuePrediction` with `outcome=uncertain` and `reason="insufficient_precedent"`. No LLM call.

2. **Construct per-issue prompt**: System prompt instructs IRAC reasoning:
   - **I**ssue: What is the specific dispute point?
   - **R**ule: What legal rules/principles apply? (from retrieved cases)
   - **A**pplication: How do the rules apply to this case's facts?
   - **C**onclusion: What is the likely outcome and amount?

3. **LLM call** (Claude Sonnet, temp=0.2):
   - Context: Issue details + top 5–8 retrieved cases for this issue + KG constraints
   - Structured output: JSON conforming to `IssuePrediction` schema
   - Token budget: ~2000 tokens per issue

4. **Extract**: Parse into `IssuePrediction` with raw (uncalibrated) confidence

**Output**: `List[IssuePrediction]`

```python
class IssuePrediction(BaseModel):
    """Prediction for a single disputed issue."""
    issue_type: IssueType
    outcome: IssueOutcome          # tenant_wins, landlord_wins, split, uncertain
    raw_confidence: float          # 0-1, uncalibrated LLM self-assessment
    calibrated_confidence: Optional[float]  # filled in Step 6
    predicted_amount: Optional[float]       # £ amount for this issue
    reasoning: str                          # IRAC-structured reasoning
    supporting_cases: List[Citation]        # cases cited for this issue
    key_factors: List[str]                  # what drove this prediction
    counterfactuals: List[Counterfactual]   # "if X were different, outcome would be Y"
    evidence_strength: EvidenceStrength     # strong, moderate, weak, insufficient
    data_completeness_impact: str           # how missing evidence affects prediction
```

```python
class Counterfactual(BaseModel):
    """What-if scenario showing sensitivity of prediction."""
    condition: str          # "If tenant had provided check-in inventory"
    alternative_outcome: str  # "Landlord's cleaning claim would likely succeed"
    confidence_shift: float   # e.g., -0.25 (confidence drops by 25pp)
```

**Cost**: 1 LLM call per issue × ~2000 tokens = ~£0.01–0.03 per issue. For 3 issues: ~£0.03–0.09.

**Fallback**: If LLM call fails or returns unparseable output, retry once. If still fails, mark issue as uncertain with raw LLM response stored in reasoning trace for debugging.

---

### 3.5 Step 4: Aggregator & Adversarial Critic

**Purpose**: Combine per-issue predictions into an overall case outcome, then run an adversarial critique pass to check consistency.

**Approach**: Inspired by multi-agent debate research (ICML 2024, CIKM 2024) which showed 15–25% improvement in strategic reasoning and 30% hallucination reduction. We use a **selective critique** strategy based on the Self-Critique Paradox finding (Snorkel AI, 2025): only critique when initial confidence is moderate (0.4–0.8), skip for high-confidence obvious cases.

**Input**: `List[IssuePrediction]`, `CaseFile`, `KnowledgeGraph`

**Process**:

1. **Deterministic Aggregation**:
   ```python
   def aggregate_issue_predictions(
       issues: List[IssuePrediction],
       case: CaseFile
   ) -> AggregatedPrediction:
       """Combine per-issue predictions into overall outcome."""
       total_deposit = case.tenancy.deposit_amount
       tenant_recovery = 0.0
       landlord_recovery = 0.0
       
       for issue in issues:
           if issue.outcome == IssueOutcome.UNCERTAIN:
               continue  # uncertain issues don't contribute to amounts
           if issue.predicted_amount is not None:
               if issue.outcome in (IssueOutcome.TENANT_WINS, IssueOutcome.SPLIT):
                   tenant_recovery += issue.predicted_amount
               if issue.outcome == IssueOutcome.LANDLORD_WINS:
                   landlord_recovery += issue.predicted_amount
       
       # Clamp to deposit amount
       tenant_recovery = min(tenant_recovery, total_deposit)
       landlord_recovery = min(landlord_recovery, total_deposit)
       
       # Determine overall outcome
       if tenant_recovery > 0.7 * total_deposit:
           overall = OutcomeType.TENANT_WIN
       elif landlord_recovery > 0.7 * total_deposit:
           overall = OutcomeType.LANDLORD_WIN
       elif any(i.outcome == IssueOutcome.UNCERTAIN for i in issues):
           overall = OutcomeType.UNCERTAIN
       else:
           overall = OutcomeType.SPLIT
       
       # Overall confidence = weighted mean of per-issue confidences
       # weighted by claimed amount (bigger issues matter more)
       weighted_conf = weighted_mean(
           [i.raw_confidence for i in issues if i.outcome != IssueOutcome.UNCERTAIN],
           [i.claimed_amount or 1.0 for i in issues if i.outcome != IssueOutcome.UNCERTAIN]
       )
       
       return AggregatedPrediction(
           overall_outcome=overall,
           raw_confidence=weighted_conf,
           tenant_recovery=tenant_recovery,
           landlord_recovery=landlord_recovery,
           issue_predictions=issues
       )
   ```

2. **Adversarial Critique** (conditional — only when `0.4 < raw_confidence < 0.8`):
   
   A single LLM call that plays **devil's advocate**:
   
   ```
   System: You are a legal reasoning critic. Your job is to find weaknesses 
   in the following prediction. Check:
   
   (a) CITATION VALIDITY: Are all cited cases actually in the retrieved set?
       List any citations that don't appear in the retrieval results.
   (b) LOGICAL CONSISTENCY: Does the reasoning contradict any facts in the 
       Knowledge Graph? (e.g., claiming damage occurred before move-in date)
   (c) MISSING EVIDENCE IMPACT: What missing evidence would change the outcome?
       How much would confidence drop?
   (d) CONFLICT DETECTION: Do per-issue predictions contradict each other?
       (e.g., finding landlord maintained property well in Issue A but neglected 
       it in Issue B)
   (e) AMOUNT REASONABLENESS: Are predicted amounts within plausible bounds?
       Does the total exceed the deposit?
   
   Return a structured critique with severity ratings.
   ```

**Output**: `CritiqueResult`

```python
class CritiqueResult(BaseModel):
    """Result of adversarial critique pass."""
    invalid_citations: List[InvalidCitation]      # citations not in retrieved set
    logical_inconsistencies: List[Inconsistency]   # contradictions with KG
    missing_evidence_impact: List[MissingEvidenceImpact]
    inter_issue_conflicts: List[IssueConflict]
    amount_issues: List[AmountIssue]
    overall_critique_severity: str  # none, minor, moderate, severe
    confidence_adjustment: float    # suggested adjustment to confidence (-0.3 to +0.1)
    should_rerun: bool             # True if severe issues found

class InvalidCitation(BaseModel):
    citation_text: str
    issue_type: IssueType
    reason: str  # "not_in_retrieved_set", "case_overruled", "misquoted"
```

**Cost**: 1 LLM call, ~1500 tokens. ~£0.01–0.02. Skipped for high-confidence cases (saves ~40% of critique calls).

**Fallback**: If critique call fails, proceed without critique but flag `critique_skipped=True` in output.

---

### 3.6 Step 5: Citation Verifier

**Purpose**: Mechanistically verify that every citation in the prediction actually exists in the retrieved case set. Zero tolerance for hallucinated case references.

**Approach**: Inspired by FACTUM (Johns Hopkins, 2026) and VeriCite (2025). Since we have a finite retrieved set, verification is deterministic — no LLM needed.

**Input**: `AggregatedPrediction`, `CritiqueResult`, `Dict[IssueType, IssueRetrievalResult]`

**Process**:

```python
def verify_citations(
    prediction: AggregatedPrediction,
    retrieval_results: Dict[IssueType, IssueRetrievalResult],
    critique: Optional[CritiqueResult]
) -> VerificationResult:
    """Verify all citations against the retrieved case index."""
    
    # Build lookup of all retrieved case references
    valid_refs = set()
    for issue_results in retrieval_results.values():
        for result in issue_results.results:
            valid_refs.add(normalize_case_ref(result.case_reference))
            valid_refs.add(normalize_case_ref(result.case_name))
    
    verified = []
    removed = []
    
    for issue_pred in prediction.issue_predictions:
        for citation in issue_pred.supporting_cases:
            normalized = normalize_case_ref(citation.case_reference)
            if normalized in valid_refs:
                # Populate similarity score from retrieval results
                citation.similarity_score = lookup_score(normalized, retrieval_results)
                citation.verified = True
                verified.append(citation)
            else:
                citation.verified = False
                removed.append(citation)
    
    # If too many citations removed, flag for re-prediction
    removal_rate = len(removed) / max(len(verified) + len(removed), 1)
    
    return VerificationResult(
        verified_citations=verified,
        removed_citations=removed,
        removal_rate=removal_rate,
        needs_reprediction=removal_rate > 0.3,  # >30% invalid → re-run
        all_citations_valid=len(removed) == 0
    )
```

**Re-prediction trigger**: If >30% of citations are invalid, re-run Step 3 for the affected issues with an enhanced prompt: `"CRITICAL: Only cite cases from the following retrieved set: {case_list}. Do not reference any other cases."`

**Output**: `VerificationResult` + cleaned `AggregatedPrediction`

**Cost**: Deterministic string matching — no LLM call. ~5ms.

---

### 3.7 Step 6: Confidence Calibrator

**Purpose**: Transform raw LLM confidence scores into empirically calibrated probabilities.

**Approach**: Based on extensive calibration research (SteeringConf 2025, QA-Calibration ICLR 2025, Dual-Align 2026). We use **isotonic regression** (non-parametric, handles arbitrary miscalibration shapes) trained on a gold-standard set, with **per-issue-type calibration** for finer granularity.

**Input**: `AggregatedPrediction` (with raw confidences), `CritiqueResult`

**Process**:

```python
class ConfidenceCalibrator:
    """Calibrates raw LLM confidence to empirical probabilities."""
    
    def __init__(self):
        # One calibrator per issue type (trained offline)
        self.calibrators: Dict[IssueType, IsotonicRegression] = {}
        # Fallback global calibrator
        self.global_calibrator: Optional[IsotonicRegression] = None
    
    def train(self, gold_set: List[GoldCase]):
        """Train calibrators on gold-standard cases with known outcomes."""
        for issue_type in IssueType:
            cases = [c for c in gold_set if c.issue_type == issue_type]
            if len(cases) >= 20:  # minimum for reliable calibration
                raw_scores = [c.raw_confidence for c in cases]
                outcomes = [c.actual_outcome_binary for c in cases]
                self.calibrators[issue_type] = IsotonicRegression(
                    out_of_bounds='clip'
                ).fit(raw_scores, outcomes)
        
        # Global fallback
        all_raw = [c.raw_confidence for c in gold_set]
        all_outcomes = [c.actual_outcome_binary for c in gold_set]
        self.global_calibrator = IsotonicRegression(
            out_of_bounds='clip'
        ).fit(all_raw, all_outcomes)
    
    def calibrate(self, prediction: AggregatedPrediction,
                  critique: Optional[CritiqueResult]) -> AggregatedPrediction:
        """Apply calibration + critique-based adjustments."""
        for issue in prediction.issue_predictions:
            # Get calibrator for this issue type (or global fallback)
            cal = self.calibrators.get(issue.issue_type, self.global_calibrator)
            if cal:
                issue.calibrated_confidence = float(
                    cal.predict([issue.raw_confidence])[0]
                )
            else:
                issue.calibrated_confidence = issue.raw_confidence
            
            # Apply critique-based adjustment
            if critique and critique.confidence_adjustment != 0:
                issue.calibrated_confidence = max(0.0, min(1.0,
                    issue.calibrated_confidence + critique.confidence_adjustment
                ))
        
        # Data quality discount
        quality_multiplier = {
            "comprehensive": 1.0,
            "adequate": 0.9,
            "minimal": 0.75,
            "insufficient": 0.5
        }.get(prediction.data_quality_tier, 0.8)
        
        prediction.overall_confidence = (
            weighted_mean_calibrated(prediction.issue_predictions) 
            * quality_multiplier
        )
        
        return prediction
```

**Training**: Offline, on the gold-standard test set (see Section 7). Retrained whenever gold set is expanded or prediction model changes.

**Output**: `AggregatedPrediction` with `calibrated_confidence` populated on all issues and overall.

**Cost**: Deterministic sklearn inference — no LLM call. ~1ms.

---

### 3.8 Step 7: Output Assembler

**Purpose**: Format the calibrated, verified prediction into the backwards-compatible `PredictionResult`.

**Input**: Calibrated `AggregatedPrediction`, `VerificationResult`, `CritiqueResult`

**Process**:
1. Map to existing `PredictionResult` schema (no breaking changes)
2. Populate `reasoning_trace` with per-step entries (issue decomposition → retrieval → prediction → critique → calibration)
3. Populate `retrieved_cases` with verified citations only
4. Generate `predicted_settlement_range` from amount predictions (±15% of central estimate, clamped to [0, deposit])
5. Generate `uncertainties`, `missing_information`, `assumptions_made` from critique results
6. Append legal disclaimer
7. Validate: `low <= high`, amounts within deposit, no legal-advice language

**Output**: `PredictionResult` (backwards-compatible)

**Cost**: Deterministic formatting — no LLM call. ~2ms.

---

### 3.9 End-to-End Cost & Latency Budget

| Step | LLM Calls | Est. Cost | Est. Latency | Parallelisable? |
|------|-----------|-----------|--------------|-----------------|
| 1. Issue Decomposer | 0 (or 1 Haiku fallback) | £0.00–0.005 | ~10ms | — |
| 2. Per-Issue Retrieval | 0 (RAG only) | £0.005 | ~1s | Yes (all issues) |
| 3. Per-Issue Predictor | N issues × 1 Sonnet | £0.03–0.09 | ~3–5s | Yes (all issues) |
| 4. Aggregator & Critic | 1 Sonnet (conditional) | £0.00–0.02 | ~0–2s | — |
| 5. Citation Verifier | 0 | £0.00 | ~5ms | — |
| 6. Calibrator | 0 | £0.00 | ~1ms | — |
| 7. Output Assembler | 0 | £0.00 | ~2ms | — |
| **Total (3 issues, critique triggered)** | **4–5 calls** | **~£0.10–0.15** | **~6–9s** | |
| **Total (5 issues, critique triggered)** | **6–7 calls** | **~£0.15–0.25** | **~8–12s** | |
| **Worst case (5 issues, re-prediction)** | **10–12 calls** | **~£0.25–0.30** | **~15–20s** | |

**Within budget**: £0.30 max cost, 45s max p95 latency. Well within targets for typical cases.

### 3.10 Cost Optimisation Strategies

1. **Prompt Caching** (Anthropic, 2025): Cache the system prompt and legal context (5K+ tokens) across calls. Up to 90% cost reduction on cached tokens. Since system prompts are identical across issues, this is highly effective.

2. **Selective Critique**: Skip adversarial critique when confidence > 0.8 or < 0.3 (obvious cases). Saves ~40% of critique calls per the Self-Critique Paradox finding.

3. **Parallel Execution**: Steps 2 and 3 execute in parallel across issues. 5 issues take the same wall-clock time as 1.

4. **Tiered Model Routing**: Use Haiku-class model for issue decomposition (Step 1 fallback) and Sonnet for prediction (Step 3) and critique (Step 4). Reserve Opus for edge cases that trigger re-prediction.

5. **Result Caching**: Cache retrieval results by (issue_type, region, key_facts_hash) with 24h TTL. Identical disputes hitting the same issue patterns reuse cached retrievals.

---

## 4. Algorithms & Models

### 4.1 Temporal Decay Function

**Rationale**: PILOT (SIGIR 2024) and ChronosLex (ACL 2024) demonstrated 15–20% accuracy improvement on recent cases when applying temporal weighting. LexTempus (ACL 2025) showed Dynamic Mixture of Experts with temporal routing achieves 20–35% improvement on unseen time periods.

**Implementation**:

```python
def temporal_relevance_score(
    case_year: int,
    query_year: int = 2026,
    half_life: float = 3.0,
    legislative_breaks: Dict[int, str] = None
) -> float:
    """
    Exponential decay with legislative regime penalties.
    
    Default half-life of 3 years means:
      - 2025 case: score = 0.79
      - 2023 case: score = 0.63
      - 2020 case: score = 0.40
      - 2017 case: score = 0.20
    
    Cases from before a legislative break get an additional 0.8x penalty
    if the break is relevant to the query issue.
    """
    age = query_year - case_year
    base_decay = 0.5 ** (age / half_life)
    
    # Legislative regime penalty
    regime_penalty = 1.0
    if legislative_breaks:
        for break_year, break_desc in legislative_breaks.items():
            if case_year < break_year:
                regime_penalty *= 0.8  # 20% penalty per relevant legislative change
    
    return base_decay * regime_penalty

# Known legislative breaks for deposit disputes
DEPOSIT_LEGISLATIVE_BREAKS = {
    2007: "Housing Act 2004 s213-215 deposit protection came into force",
    2015: "Deregulation Act 2015 changed s21/deposit protection interaction",
    2019: "Tenant Fees Act 2019 banned most letting fees, capped deposits at 5 weeks",
}
```

**Tuning**: Half-life is a hyperparameter. Test values {2, 3, 4, 5} on temporal holdout set. Report ablation in thesis.

### 4.2 Multi-Party Evidence Weighting

**Rationale**: When both tenant and landlord provide evidence, conflicting claims need principled resolution. The Contestable AI framework (2024) uses argument graphs with attack/support relationships. MAD-Sherlock (2024) showed 15–20% improvement in detecting false claims via multi-perspective debate.

**Evidence Credibility Hierarchy** (based on tribunal adjudication principles):

```python
EVIDENCE_WEIGHT = {
    # Documentary > Testimonial
    "signed_inventory":       1.0,   # Gold standard: signed by both parties
    "professional_report":    0.95,  # Check-out clerk, surveyor report
    "dated_photograph":       0.90,  # Timestamped photos
    "invoice_receipt":        0.85,  # Professional cleaning/repair receipts
    "bank_statement":         0.80,  # Payment records
    "correspondence":         0.75,  # Emails, letters between parties
    "undated_photograph":     0.60,  # Photos without timestamps
    "witness_statement":      0.50,  # Third-party testimony
    "party_testimony":        0.40,  # Self-serving claim by either party
    "verbal_claim":           0.20,  # Unsupported verbal assertion
}

# Contemporaneous > Retrospective
TIMING_MODIFIER = {
    "at_time_of_event":       1.0,   # Created when event occurred
    "within_30_days":         0.9,   # Created shortly after
    "within_6_months":        0.7,   # Some delay
    "after_dispute_started":  0.5,   # Potentially biased by dispute
}

# Corroborated > Uncorroborated
CORROBORATION_MODIFIER = {
    "corroborated_by_both":   1.0,   # Both parties agree
    "corroborated_by_third":  0.9,   # Independent witness/document
    "corroborated_by_other":  0.8,   # Supported by other evidence
    "uncorroborated":         0.6,   # Standalone evidence
    "contradicted":           0.3,   # Other evidence disagrees
}

def evidence_credibility(evidence: EvidenceItem) -> float:
    """Compute overall credibility score for a piece of evidence."""
    base = EVIDENCE_WEIGHT.get(evidence.evidence_type, 0.5)
    timing = TIMING_MODIFIER.get(evidence.timing_category, 0.7)
    corroboration = CORROBORATION_MODIFIER.get(evidence.corroboration_status, 0.6)
    return base * timing * corroboration
```

**Conflict Resolution**: When tenant and landlord evidence directly conflict on the same issue:
1. Score both sides' evidence using the credibility function
2. Higher credibility evidence gets priority in the prompt context
3. Include both sides but annotate: `"[Tenant evidence, credibility=0.75] vs [Landlord evidence, credibility=0.45]"`
4. The per-issue predictor (Step 3) is instructed to weight accordingly

### 4.3 Ensemble Strategy (Phase 2 Enhancement)

**Rationale**: "Wisdom of the Silicon Crowd" (2024) showed LLM ensembles match human forecasting accuracy. Beyond Majority Voting (2025) demonstrated 15–25% improvement with weighted aggregation. However, multi-model ensembles are expensive.

**Approach**: Rather than multi-model (which costs 3–5x), we use **multi-prompting-strategy ensemble** with a single model:

```python
class PromptStrategyEnsemble:
    """Run same case through different prompting strategies, aggregate."""
    
    STRATEGIES = {
        "evidence_first": "Start by analysing the evidence, then apply legal rules.",
        "precedent_first": "Start by finding the most similar precedent, then compare facts.",
        "issue_first": "Start by identifying the key legal issue, then evaluate evidence.",
    }
    
    async def predict_with_ensemble(
        self, issue: IssueContext, retrieval: IssueRetrievalResult
    ) -> EnsemblePrediction:
        # Run all strategies in parallel
        predictions = await asyncio.gather(*[
            self.predict_with_strategy(issue, retrieval, strategy, instruction)
            for strategy, instruction in self.STRATEGIES.items()
        ])
        
        # Aggregate
        outcomes = [p.outcome for p in predictions]
        confidences = [p.raw_confidence for p in predictions]
        
        # Majority vote for outcome
        majority_outcome = Counter(outcomes).most_common(1)[0][0]
        
        # Disagreement as uncertainty signal
        agreement_rate = max(Counter(outcomes).values()) / len(outcomes)
        if agreement_rate < 0.67:  # No clear majority
            return EnsemblePrediction(
                outcome=IssueOutcome.UNCERTAIN,
                confidence=mean(confidences) * 0.5,  # Penalise for disagreement
                disagreement_flag=True,
                strategy_predictions=predictions
            )
        
        return EnsemblePrediction(
            outcome=majority_outcome,
            confidence=mean([c for p, c in zip(predictions, confidences) 
                           if p.outcome == majority_outcome]),
            disagreement_flag=False,
            strategy_predictions=predictions
        )
```

**Cost**: 3x the per-issue prediction cost. Only enable for high-stakes cases (deposit > £1000 or user requests detailed analysis). For standard cases, use single-strategy prediction (Step 3).

---

## 5. Quality & Safety

### 5.1 Hallucination Prevention (Multi-Layer)

| Layer | Mechanism | Where |
|-------|-----------|-------|
| **L1: Retrieval grounding** | Cite-or-abstain gate — no prediction without sufficient retrieved cases | Step 2 |
| **L2: Constrained generation** | Structured output (Anthropic JSON schema) forces schema compliance | Step 3 |
| **L3: Prompt instruction** | System prompt explicitly lists available cases: "ONLY cite from this list" | Step 3 |
| **L4: Deterministic verification** | String-match every citation against retrieved set | Step 5 |
| **L5: Adversarial critique** | Critic LLM checks citation validity, logical consistency | Step 4 |
| **L6: Re-prediction** | If >30% citations invalid, re-run with stricter prompt | Step 5 |

**Target**: Citation precision > 98% (< 2% hallucinated citations). Measured on gold set.

### 5.2 Bias Detection & Fairness Monitoring

**Approach**: Informed by JudiFair (ICLR 2026) which found severe and pervasive unfairness across 16 LLMs on legal tasks, and the comprehensive fairness framework from AI Fairness 360.

**Metrics tracked** (on gold set and production predictions):

```python
class FairnessMetrics(BaseModel):
    """Tracked for each prediction batch."""
    # Demographic parity: prediction rates by group
    tenant_win_rate_by_region: Dict[str, float]     # London vs Manchester vs etc.
    tenant_win_rate_by_deposit_band: Dict[str, float]  # <500, 500-1000, 1000+
    tenant_win_rate_by_issue_type: Dict[str, float]
    
    # Calibration by subgroup: ECE per group
    ece_by_region: Dict[str, float]
    ece_by_issue_type: Dict[str, float]
    
    # Amount fairness
    mean_recovery_pct_by_region: Dict[str, float]  # % of deposit recovered
    
    # Alert thresholds
    max_parity_gap: float = 0.10  # Flag if any group differs by >10%
    max_ece_gap: float = 0.05     # Flag if ECE differs by >5% across groups
```

**Audit cadence**: After every 100 predictions or monthly, whichever comes first. Alert if thresholds breached.

### 5.3 Uncertainty Quantification

**Approach**: Informed by "To Believe or Not to Believe Your LLM" (Google DeepMind, 2025) which distinguishes epistemic from aleatoric uncertainty using iterative prompting.

```python
class UncertaintyDecomposition(BaseModel):
    """Decompose total uncertainty into sources."""
    
    epistemic_uncertainty: float   # model doesn't know — can be reduced with more data
    # Sources: few similar cases, novel issue type, model disagreement
    
    aleatoric_uncertainty: float   # inherently uncertain — can't be reduced
    # Sources: conflicting evidence, borderline case, judge discretion
    
    data_uncertainty: float        # input quality — can be reduced with more evidence
    # Sources: missing evidence, incomplete CaseFile, low data_quality_tier
    
    dominant_type: str             # "epistemic", "aleatoric", or "data"
    explanation: str               # human-readable explanation of main uncertainty source
    
    @classmethod
    def compute(cls, issue_pred: IssuePrediction, 
                retrieval: IssueRetrievalResult,
                case_file: CaseFile) -> "UncertaintyDecomposition":
        
        # Epistemic: few cases, novel issue
        n_cases = len(retrieval.results)
        max_similarity = max((r.semantic_score for r in retrieval.results), default=0)
        epistemic = 1.0 - min(n_cases / 10, 1.0) * max_similarity
        
        # Data: input completeness
        data = 1.0 - issue_pred.data_completeness
        
        # Aleatoric: inherent ambiguity (approximated by ensemble disagreement 
        # or confidence spread in retrieved cases)
        outcome_spread = compute_outcome_spread(retrieval.results)
        aleatoric = outcome_spread  # high spread → high inherent uncertainty
        
        # Normalise
        total = epistemic + aleatoric + data
        if total > 0:
            epistemic /= total
            aleatoric /= total
            data /= total
        
        dominant = max(
            [("epistemic", epistemic), ("aleatoric", aleatoric), ("data", data)],
            key=lambda x: x[1]
        )[0]
        
        return cls(
            epistemic_uncertainty=round(epistemic, 3),
            aleatoric_uncertainty=round(aleatoric, 3),
            data_uncertainty=round(data, 3),
            dominant_type=dominant,
            explanation=cls._explain(dominant, epistemic, aleatoric, data)
        )
```

### 5.4 Graceful Degradation

| Condition | Response |
|-----------|----------|
| RAG returns 0 results for all issues | Return `PredictionResult.create_uncertain(reason="no_similar_cases")` |
| RAG returns < min_cases for some issues | Predict on issues with sufficient cases; mark others `uncertain` |
| KG is empty/invalid | Fall back to flat query string (V1 behaviour) for retrieval |
| LLM call fails after retry | Mark affected issues `uncertain`; if >50% issues fail, return overall `uncertain` |
| Citation verification removes >50% citations | Return overall `uncertain` with explanation |
| All per-issue predictions disagree with each other | Escalate to ensemble (if not already); if still disagree, return `uncertain` |
| CaseFile has `insufficient` data quality | Cap overall confidence at 0.4; add prominent uncertainty note |

---

## 6. Data Models

### 6.1 New Models (Pipeline-Internal)

```python
# ── Issue Decomposition ──

class IssueType(str, Enum):
    CLEANING = "cleaning"
    DAMAGE = "damage"
    RENT_ARREARS = "rent_arrears"
    REDECORATION = "redecoration"
    DEPOSIT_PROTECTION = "deposit_protection"
    INVENTORY = "inventory"
    GARDEN = "garden"
    KEYS = "keys"
    UTILITIES = "utilities"
    OTHER = "other"

class ClaimDetail(BaseModel):
    party: str            # "tenant" or "landlord"
    issue_type: IssueType
    claimed_amount: Optional[float]
    description: str
    supporting_evidence_ids: List[str]

class EvidenceConflict(BaseModel):
    issue_type: IssueType
    tenant_position: str
    landlord_position: str
    tenant_evidence: List[str]
    landlord_evidence: List[str]
    resolution_hint: str   # from KG consistency checks

class TimelineEvent(BaseModel):
    date: Optional[date]
    description: str
    source: str            # "tenant", "landlord", "document"
    relevance_to_issue: str

class IssueContext(BaseModel):
    """Complete context for predicting a single issue."""
    issue_type: IssueType
    issue_description: str
    tenant_claim: Optional[ClaimDetail]
    landlord_claim: Optional[ClaimDetail]
    supporting_evidence: List[EvidenceItem]
    timeline_events: List[TimelineEvent]
    kg_constraints: List[str]
    evidence_conflicts: List[EvidenceConflict]
    claimed_amount: Optional[float]
    data_completeness: float  # 0-1


# ── Retrieval ──

class IssueRetrievalResult(BaseModel):
    issue_type: IssueType
    query_used: str
    results: List[RetrievalResult]
    rag_confidence: float
    temporal_distribution: Dict[int, int]
    legislative_regime: str
    is_sufficient: bool


# ── Prediction ──

class IssueOutcome(str, Enum):
    TENANT_WINS = "tenant_wins"
    LANDLORD_WINS = "landlord_wins"
    SPLIT = "split"
    UNCERTAIN = "uncertain"

class EvidenceStrength(str, Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    INSUFFICIENT = "insufficient"

class Counterfactual(BaseModel):
    condition: str
    alternative_outcome: str
    confidence_shift: float

class IssuePrediction(BaseModel):
    """Enhanced per-issue prediction."""
    issue_type: IssueType
    outcome: IssueOutcome
    raw_confidence: float
    calibrated_confidence: Optional[float]
    predicted_amount: Optional[float]
    reasoning: str
    supporting_cases: List[Citation]
    key_factors: List[str]
    counterfactuals: List[Counterfactual]
    evidence_strength: EvidenceStrength
    data_completeness_impact: str
    uncertainty: Optional[UncertaintyDecomposition]


# ── Critique ──

class InvalidCitation(BaseModel):
    citation_text: str
    issue_type: IssueType
    reason: str

class Inconsistency(BaseModel):
    description: str
    severity: str   # "minor", "moderate", "severe"
    affected_issues: List[IssueType]

class MissingEvidenceImpact(BaseModel):
    missing_evidence: str
    affected_issue: IssueType
    estimated_confidence_impact: float
    estimated_outcome_change: Optional[str]

class CritiqueResult(BaseModel):
    invalid_citations: List[InvalidCitation]
    logical_inconsistencies: List[Inconsistency]
    missing_evidence_impact: List[MissingEvidenceImpact]
    inter_issue_conflicts: List[str]
    amount_issues: List[str]
    overall_critique_severity: str
    confidence_adjustment: float
    should_rerun: bool


# ── Verification ──

class VerificationResult(BaseModel):
    verified_citations: List[Citation]
    removed_citations: List[Citation]
    removal_rate: float
    needs_reprediction: bool
    all_citations_valid: bool


# ── Calibration ──

class UncertaintyDecomposition(BaseModel):
    epistemic_uncertainty: float
    aleatoric_uncertainty: float
    data_uncertainty: float
    dominant_type: str
    explanation: str


# ── Fairness ──

class FairnessMetrics(BaseModel):
    tenant_win_rate_by_region: Dict[str, float]
    tenant_win_rate_by_deposit_band: Dict[str, float]
    tenant_win_rate_by_issue_type: Dict[str, float]
    ece_by_region: Dict[str, float]
    ece_by_issue_type: Dict[str, float]
    mean_recovery_pct_by_region: Dict[str, float]
    flagged_biases: List[str]
```

### 6.2 Output Model (Backwards-Compatible)

The existing `PredictionResult` schema is preserved. New fields are **additive only** (Optional fields with defaults):

```python
class PredictionResult(BaseModel):
    """Backwards-compatible output. New fields are Optional."""
    
    # ── Existing fields (unchanged) ──
    overall_outcome: OutcomeType
    overall_confidence: float
    outcome_summary: str
    tenant_recovery_amount: Optional[float]
    landlord_recovery_amount: Optional[float]
    predicted_settlement_range: Optional[SettlementRange]
    issue_predictions: List[IssuePrediction]
    reasoning_trace: List[ReasoningStep]
    key_strengths: List[str]
    key_weaknesses: List[str]
    uncertainties: List[str]
    missing_information: List[str]
    assumptions_made: List[str]
    retrieved_cases: List[str]
    rag_confidence: float
    disclaimer: str
    
    # ── New V2 fields (all Optional, backwards-compatible) ──
    pipeline_version: str = "v2"
    calibrated_confidence: Optional[float] = None       # post-calibration
    confidence_calibrated: bool = False                  # whether calibration was applied
    uncertainty_decomposition: Optional[UncertaintyDecomposition] = None
    critique_result: Optional[CritiqueResult] = None
    citation_verification: Optional[VerificationResult] = None
    temporal_distribution: Optional[Dict[int, int]] = None  # year → case count
    ensemble_used: bool = False
    ensemble_agreement_rate: Optional[float] = None
    fairness_flags: List[str] = []
    pipeline_metadata: Optional[PipelineMetadata] = None

class PipelineMetadata(BaseModel):
    """Metadata about the prediction pipeline execution."""
    total_llm_calls: int
    total_tokens_used: int
    estimated_cost_gbp: float
    total_latency_ms: int
    steps_executed: List[str]
    critique_triggered: bool
    reprediction_triggered: bool
    issues_decomposed: int
    issues_with_sufficient_cases: int
    fallbacks_used: List[str]
```

---

## 7. Evaluation Framework

### 7.1 Gold Standard Test Set

**Composition** (target: 100 cases):

| Category | Count | Source | Purpose |
|----------|-------|--------|---------|
| Temporal holdout (2024–2025) | 40 | Recent BAILII cases | Test temporal generalisation |
| Multi-issue complex cases | 25 | Cases with 3+ disputed issues | Test decomposition |
| Edge cases | 15 | Conflicting evidence, missing inventory, deposit not protected | Test robustness |
| Adversarial | 10 | Manually crafted ambiguous cases | Test uncertainty handling |
| Simple cases | 10 | Clear-cut single-issue cases | Baseline sanity check |

**Annotation schema** (per case):
- `actual_outcome`: tenant_win / landlord_win / split
- `actual_amounts`: per-issue amounts awarded
- `relevant_legal_principles`: what the judge cited
- `key_evidence_used`: what evidence was decisive
- `complexity_rating`: simple / moderate / complex
- `annotator_confidence`: how clear the outcome was

**Annotation process**:
1. First pass: CS researcher extracts structured data from decision text
2. Second pass: Independent annotator verifies
3. Disagreements: Resolved by consulting the decision text (ground truth)
4. Inter-annotator agreement target: Cohen's κ > 0.8

### 7.2 Metrics

| Metric | Definition | Target | Measured On |
|--------|-----------|--------|-------------|
| **3-class Accuracy** | % correct (tenant_win / landlord_win / split) | ≥ 70% | Gold set |
| **Per-issue Accuracy** | % correct per issue type | ≥ 65% per type | Gold set |
| **Brier Score** | Mean squared error of probability predictions | < 0.20 | Gold set |
| **ECE** | Expected Calibration Error (10 bins) | < 0.05 | Gold set |
| **Citation Precision** | % of citations that appear in retrieved set | > 98% | All predictions |
| **Citation Recall** | % of relevant retrieved cases actually cited | > 60% | Gold set |
| **Hallucination Rate** | % of predictions with any invalid citation | < 2% | All predictions |
| **Settlement Range MAE** | Mean absolute error of predicted vs actual amounts | < £150 | Gold set (where amounts known) |
| **Temporal Accuracy** | Accuracy on 2024–2025 cases specifically | ≥ 65% | Temporal holdout |
| **Latency p95** | 95th percentile end-to-end time | < 45s | Production |
| **Cost per prediction** | LLM + embedding costs | < £0.30 | Production |

### 7.3 Ablation Study Design

Each ablation removes one component and measures degradation:

| Configuration | What's Changed | Expected Result |
|---------------|---------------|-----------------|
| **Baseline (V1)** | Single-shot, flat query, no verification | Benchmark |
| **V2 Full** | All steps enabled | Best performance |
| **V2 – Decomposition** | Single query instead of per-issue | ~8–12% accuracy drop |
| **V2 – KG Queries** | Flat query string instead of KG-shaped | ~10–15% retrieval precision drop |
| **V2 – Temporal Decay** | Uniform case weighting | ~5–10% accuracy drop on recent cases |
| **V2 – Citation Verification** | No post-hoc verification | Citation precision drops to ~85–90% |
| **V2 – Critique** | No adversarial critique | Consistency issues increase |
| **V2 – Calibration** | Raw confidence only | ECE increases by 0.05–0.15 |
| **RAG-only** | No KG at all | Drop in multi-issue handling |
| **KG-only** | No RAG retrieval | Major accuracy drop (no precedent) |
| **Proposition-PageRank** *(Phase 2, post SHA-36)* | Replace chunk-grained RAG with HippoRAG-style PageRank over proposition KG; substrate built in [PR #15](https://github.com/MSH4R1F/proposer/pull/15) | Hypothesised gain on multi-hop / cross-paragraph reasoning per Dense X (2312.06648) and HippoRAG (NeurIPS 2024); ablation will be RAGAS-scored (faithfulness, context precision/recall) |

### 7.4 Online Evaluation (A/B Testing)

**Framework**: Log-based evaluation with offline analysis (no real-time A/B split needed for MVP).

1. **Shadow mode**: Run V2 pipeline alongside V1 for 2 weeks. Compare outputs without exposing V2 to users.
2. **Metrics comparison**: Accuracy (where outcome is known), confidence calibration, citation validity, latency, cost.
3. **Prompt variation testing**: Use Braintrust or LangSmith to test prompt variations:
   - IRAC-structured vs. free-form reasoning
   - Evidence-first vs. precedent-first vs. issue-first ordering
   - Strict vs. flexible citation instructions

### 7.5 Feedback Loop (Future)

```python
class OutcomeFeedback(BaseModel):
    """Collected when actual tribunal outcome is known."""
    case_id: str
    prediction_id: str
    actual_outcome: OutcomeType
    actual_amounts: Dict[IssueType, float]
    actual_total_recovery: float
    feedback_source: str  # "tribunal_decision", "user_reported", "settlement"
    feedback_date: date

class CalibrationUpdate:
    """Periodically retrain calibrators with new feedback."""
    
    def update(self, new_feedback: List[OutcomeFeedback]):
        # Add to gold set (if verified)
        # Retrain isotonic regression
        # Recalculate Brier score and ECE
        # Alert if calibration degrades
        pass
```

---

## 8. Implementation Plan

### Phase 1: Foundation (Weeks 1–2) — Maximum Impact, Minimum Risk

**Goal**: Build evaluation framework + citation verification + KG-enhanced queries. These are high-impact, low-risk improvements that don't change the core prediction flow.

| Task | Effort | Dependencies | Impact |
|------|--------|-------------|--------|
| **Gold standard test set** (50 cases) | 3 days | Manual annotation | Enables all measurement |
| **Evaluation pipeline** (accuracy, Brier, ECE) | 2 days | Gold set | Baseline metrics |
| **Citation verification** (Step 5) | 1 day | None | Eliminates hallucinated citations |
| **KG-enhanced query building** (Step 2, basic) | 2 days | Existing KG builder | Better retrieval per issue |
| **Temporal decay in reranker** | 0.5 days | None | Better recent-case handling |

**Deliverable**: Baseline accuracy measured. Citation verification live. KG queries improving retrieval.

### Phase 2: Multi-Step Pipeline (Weeks 3–4) — Core Architecture Change

**Goal**: Implement issue decomposition and per-issue prediction. This is the biggest architectural change.

| Task | Effort | Dependencies | Impact |
|------|--------|-------------|--------|
| **Issue Decomposer** (Step 1) | 2 days | KG builder | Foundation for per-issue prediction |
| **Per-issue predictor** (Step 3) | 3 days | Steps 1, 2 | Per-issue predictions with IRAC reasoning |
| **Aggregator** (Step 4, deterministic part) | 1 day | Step 3 | Overall outcome from per-issue |
| **Output assembler** (Step 7) | 1 day | Steps 4, 5 | Backwards-compatible PredictionResult |
| **Integration tests** | 2 days | All above | End-to-end pipeline works |

**Deliverable**: Full multi-step pipeline running. Ablation study: V2 vs V1 on gold set.

### Phase 3: Quality Layer (Weeks 5–6) — Calibration, Critique, Polish

**Goal**: Add calibration, adversarial critique, uncertainty quantification. Polish for thesis-quality results.

| Task | Effort | Dependencies | Impact |
|------|--------|-------------|--------|
| **Confidence calibrator** (Step 6) | 2 days | Gold set with predictions | Calibrated probabilities |
| **Adversarial critic** (Step 4, critique part) | 2 days | Step 3 working | Consistency checking |
| **Uncertainty decomposition** | 1 day | Steps 3, 6 | Epistemic vs aleatoric breakdown |
| **Evidence credibility weighting** | 2 days | KG builder | Better multi-party handling |
| **Expand gold set to 100 cases** | 3 days | Phase 1 gold set | More reliable metrics |
| **Full ablation study** | 2 days | All above | Thesis results |

**Deliverable**: Calibrated, critiqued predictions. Full ablation results. Publication-quality metrics.

### Phase 4: Advanced (Weeks 7–8, if time permits) — Ensemble, Fairness, Optimisation

| Task | Effort | Dependencies | Impact |
|------|--------|-------------|--------|
| **Multi-strategy ensemble** | 3 days | Phase 2 | Disagreement-as-uncertainty |
| **Fairness audit pipeline** | 2 days | Gold set | Bias detection |
| **Prompt caching** | 0.5 days | Anthropic API | 50–90% cost reduction |
| **Counterfactual explanations** | 2 days | Step 3 | User-facing "what-if" |
| **Reliability diagrams** | 1 day | Phase 3 | Visual calibration proof |

**Deliverable**: Production-ready prediction engine with fairness guarantees and cost optimisation.

---

## 9. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Multi-step increases latency beyond 45s** | Medium | High | Parallel execution of Steps 2/3; prompt caching; timeout gates per step |
| **Multi-step increases cost beyond £0.30** | Low | Medium | Selective critique; prompt caching; Haiku for decomposition; monitor per-prediction costs |
| **Per-issue decomposition misidentifies issues** | Medium | Medium | Fallback to V1 flat query if decomposition fails; KG provides structured issues |
| **Calibrator overfits to small gold set** | Medium | High | Leave-one-out cross-validation; monitor calibration drift on new cases; retrain monthly |
| **Temporal decay penalises still-relevant older cases** | Low | Medium | Tunable half-life; exempt "landmark" cases with high citation counts; ablation on temporal holdout |
| **Adversarial critique introduces false negatives** | Low | Medium | Only trigger for moderate-confidence cases (Self-Critique Paradox); human review of critique disagreements |
| **Gold set annotation errors** | Medium | High | Double annotation; Cohen's κ > 0.8; expert adjudication of disagreements |
| **Backwards incompatibility in PredictionResult** | Low | High | All new fields Optional with defaults; integration tests against V1 consumers |

---

## 10. Success Criteria

### 10.1 Technical (Measured on Gold Set)

- [ ] **Accuracy**: 3-class outcome accuracy ≥ 70% (V1 baseline measured first)
- [ ] **Calibration**: ECE < 0.05, Brier Score < 0.20
- [ ] **Citation integrity**: Citation precision > 98%, hallucination rate < 2%
- [ ] **Per-issue accuracy**: ≥ 65% per issue type
- [ ] **Settlement MAE**: < £150 where amounts known
- [ ] **Temporal robustness**: ≥ 65% accuracy on 2024–2025 holdout

### 10.2 Operational

- [ ] **Latency**: p95 < 45 seconds
- [ ] **Cost**: Mean < £0.20, max < £0.30 per prediction
- [ ] **Reliability**: No uncaught exceptions; graceful degradation to `uncertain`
- [ ] **Backwards compatibility**: V1 API consumers work without changes

### 10.3 Research (Thesis)

- [ ] **H1–H6** tested via ablation study with statistical significance
- [ ] **Ablation table** showing contribution of each component
- [ ] **Reliability diagram** demonstrating calibration improvement
- [ ] **Fairness audit** showing no systematic bias (< 10% parity gap)
- [ ] **Comparison** with pure RAG and pure KG baselines

### 10.4 Product

- [ ] Users see per-issue breakdown (not just overall outcome)
- [ ] Users see confidence that is empirically meaningful
- [ ] Users can trace any claim to a specific cited case
- [ ] Uncertain predictions clearly explain *why* they're uncertain
- [ ] Settlement range is plausible (within deposit, low ≤ high)

---

## 11. Academic References

### Legal AI Prediction
- **PILOT**: Cao et al. "Legal Case Outcome Prediction with Case Law" (SIGIR 2024). Precedent retrieval + temporal handling for case law systems.
- **AnnoCaseLaw**: Oxford (2025). 471 annotated cases with explainable judgment prediction.
- **ADAPT**: "Enabling Discriminative Reasoning in LLMs for Legal Judgment Prediction" (EMNLP 2024). Issue decomposition with 12–18% accuracy improvement.
- **CourtReasoner**: Han et al., Yale (EMNLP 2025). Multi-agent legal reasoning with adversarial argument construction.
- **Legal-R1**: Hu et al. "Test-Time Scaling for Legal Reasoning" (EMNLP 2025). Chain-of-thought for legal tasks.
- **Chain of Logic**: Servantez et al. "Rule-Based Reasoning with LLMs" (ACL 2024). IRAC-inspired decomposition.

### Calibration & Uncertainty
- **SteeringConf**: "Calibrating LLM Confidence with Semantic Steering" (2025). No-fine-tuning calibration.
- **QA-Calibration**: Manggala et al. (ICLR 2025). Distribution-free calibration guarantees.
- **Dual-Align**: "Unlocking Pre-Trained Model as Dual-Alignment Calibrator" (2026). Post-training calibration.
- **Conformal Prediction**: Angelopoulos & Bates. "A Gentle Introduction to Conformal Prediction" (2023).

### Knowledge Graphs & GraphRAG
- **Microsoft GraphRAG**: "From Local to Global" (2024). Hierarchical KG + community summaries.
- **Ontology-Driven Graph RAG for Legal Norms**: arXiv:2505.00039 (2025). Temporal legal ontologies.
- **Smart-Slic**: "Bridging Legal Knowledge and AI" (2025). Hierarchical NMFk for case law.

### RAG & Retrieval
- **Summary-Augmented Chunking**: "Towards Reliable Retrieval in RAG Systems for Large Legal Datasets" (ACL 2025).
- **Self-RAG**: "Self-Reflective Retrieval-Augmented Generation" (2024). Adaptive retrieval.
- **CRAG**: Corrective RAG with retrieval quality evaluation (2024).

### Hallucination & Verification
- **FACTUM**: Dassen et al. "Mechanistic Detection of Citation Hallucination" (2026). Attention pathway analysis.
- **VeriCite**: Qian et al. "Reliable Citations in RAG via Rigorous Verification" (2025).
- **RAGTruth**: Wood & Forbes. "100% Elimination of Hallucinations" (2024).
- **Legal RAG Hallucinations**: Stanford Law (JELS 2025). Hallucination rates in commercial legal AI.

### Fairness & Evaluation
- **JudiFair**: (ICLR 2026). 177K cases, 65 fairness labels across 16 LLMs.
- **LegalBench**: Stanford (2024). 162 legal reasoning evaluation tasks.
- **RAGAS**: Exploding Gradients. RAG evaluation framework (faithfulness, relevancy, precision, recall).

### Multi-Agent & Self-Verification
- **Multi-Agent Debate**: MIT/Google Brain (ICML 2024). 15–25% improvement on strategic reasoning.
- **Self-Critique Paradox**: Snorkel AI (2025). Self-critique hurts high-performance tasks.
- **Reflexion**: Shinn et al. (NeurIPS 2023). Verbal reinforcement learning.
- **Chain of Verification**: Meta AI (ACL 2024). 25–40% hallucination reduction.

### Cost Optimisation
- **LLM Shepherding**: (2026). 42–94% cost reduction via small-model hints.
- **Prompt Caching**: Anthropic (2025). 90% cost reduction on cached tokens.
- **Speculative Cascades**: Google (ICLR 2025). 2–4x speedup.

---

## 12. Open Questions

1. **Calibrator training set size**: Is 50–100 cases sufficient for reliable isotonic regression per issue type? May need global calibrator fallback for rare issue types.
2. **Ensemble cost justification**: Is 3x cost of ensemble justified by accuracy improvement? Need ablation data to decide.
3. **Temporal half-life**: Optimal half-life for deposit disputes specifically? May differ from general case law (deposit rules are relatively stable).
4. **Legislative change detection**: Should cases from before a legislative change be excluded entirely, or just down-weighted? Different issues may need different treatment.
5. **Structured output reliability**: Anthropic's native JSON schema support vs. prompt-based JSON extraction — which gives better output quality for legal reasoning?
6. **Gold set expansion**: Can we use actual Proposer user outcomes (when reported) to expand the gold set? Quality control needed.
7. **Multi-party merge strategy**: When both tenant and landlord submit evidence via the platform, should we build separate KGs and merge, or one combined KG from the start?

---

## 13. Glossary

| Term | Definition |
|------|-----------|
| **Cite-or-abstain** | Core safety rule: no prediction without retrieval-backed evidence |
| **ECE** | Expected Calibration Error — measures gap between predicted and actual probabilities |
| **Brier Score** | Mean squared error of probability predictions (0 = perfect, 1 = worst) |
| **IRAC** | Issue-Rule-Application-Conclusion — standard legal reasoning framework |
| **KG** | Knowledge Graph — structured representation of case facts and relationships |
| **RAG** | Retrieval-Augmented Generation — LLM generation grounded in retrieved documents |
| **RRF** | Reciprocal Rank Fusion — method for combining multiple ranked retrieval results |
| **ZOPA** | Zone of Possible Agreement — range where both parties would accept settlement |
| **Epistemic uncertainty** | Uncertainty from model's lack of knowledge (reducible with more data) |
| **Aleatoric uncertainty** | Inherent randomness in outcomes (irreducible) |
| **Isotonic regression** | Non-parametric calibration method fitting a monotonic function |
| **Temporal decay** | Weighting scheme that reduces relevance of older cases |
| **GraphRAG** | RAG enhanced with knowledge graph structure for retrieval and reasoning |

---

**Document Owner**: Engineering  
**Reviewer**: Mohamed Sharif  
**Next Review**: After Phase 1 completion (baseline metrics established)
