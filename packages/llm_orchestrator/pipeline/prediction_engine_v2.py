"""
Prediction Engine V2 — Multi-step reasoning pipeline orchestrator.

Wires together: Issue Decomposer → Per-Issue Retrieval → Per-Issue Predictor
→ Citation Verifier → Output Assembler.
"""

import time
from typing import Any, Dict, List, Optional

import structlog

from ..clients.base import BaseLLMClient
from ..models.case_file import CaseFile
from ..models.prediction_v2 import (
    IssueContext,
    IssueOutcome,
    IssueRetrievalResult,
    IssueType,
    PipelineMetadata,
    PredictionMode,
    PredictionResult,
    RetrievalStrategy,
)
from .citation_verifier import CitationVerifier
from .issue_decomposer import IssueDecomposer
from .issue_predictor import IssuePredictor
from .issue_retrieval import IssueRetriever
from .kg_facts import KGFacts, derive_kg_facts
from .output_assembler import OutputAssembler

logger = structlog.get_logger()


class PredictionEngineV2:
    """
    Multi-step prediction pipeline (V2).

    Signature-compatible with V1 PredictionEngine so PredictionService
    can swap in without API changes.
    """

    def __init__(
        self,
        llm_client: BaseLLMClient,
        rag_pipeline: Optional[Any] = None,
        min_confidence: float = 0.5,
        min_cases_required: int = 3,
        proposition_retriever: Optional[Any] = None,
        retrieval_strategy: RetrievalStrategy = RetrievalStrategy.CHUNK_RAG,
        *,
        prompt_pack: Optional[Any] = None,
    ):
        self.llm = llm_client
        self.rag = rag_pipeline
        self.min_confidence = min_confidence
        self.min_cases_required = min_cases_required
        self.proposition_retriever = proposition_retriever
        self.retrieval_strategy = retrieval_strategy
        # SHA-20 Phase 6: optional prompt pack. When None, the legacy IRAC
        # prompts are used (deposit baseline). When set, the pack's
        # prediction_system text takes over and downstream callers can read
        # ``self.prompt_pack`` to introspect the active pack/hash.
        self.prompt_pack = prompt_pack

        self.issue_decomposer = IssueDecomposer()
        self.issue_retriever = IssueRetriever(
            rag_pipeline,
            min_cases_required,
            proposition_retriever=proposition_retriever,
        )
        self.issue_predictor = IssuePredictor(llm_client, prompt_pack=prompt_pack)
        self.citation_verifier = CitationVerifier()
        self.output_assembler = OutputAssembler()

    def set_rag_pipeline(self, rag_pipeline: Any) -> None:
        self.rag = rag_pipeline
        self.issue_retriever = IssueRetriever(
            rag_pipeline,
            self.min_cases_required,
            proposition_retriever=self.proposition_retriever,
        )

    def set_proposition_retriever(self, proposition_retriever: Any) -> None:
        self.proposition_retriever = proposition_retriever
        self.issue_retriever = IssueRetriever(
            self.rag,
            self.min_cases_required,
            proposition_retriever=proposition_retriever,
        )

    async def predict(
        self,
        case_file: CaseFile,
        knowledge_graph: Optional[Any] = None,
        top_k: int = 10,
        mode: PredictionMode = PredictionMode.HYBRID,
        retrieval_strategy: Optional[RetrievalStrategy] = None,
        *,
        matter_type: Optional[str] = None,
    ) -> PredictionResult:
        start_time = time.time()
        strategy = retrieval_strategy or self.retrieval_strategy
        # Reset stale KG metadata from any prior call on this engine instance.
        # Critical for batch / multi-mode runs that reuse the same predictor:
        # the LLM_ONLY branch of ``_predict_issue_no_rag`` does not touch
        # ``_last_kg_metadata``, so without this reset a prior HYBRID/KG_ONLY
        # call could leak ``kg_used_for_prediction`` into a subsequent
        # LLM_ONLY artifact's ``pipeline_metadata``.
        self.issue_predictor._last_kg_metadata = {}
        metadata = PipelineMetadata(
            mode=mode.value,
            retrieval_strategy=strategy.value,
        )

        logger.info(
            "prediction_v2_starting",
            case_id=case_file.case_id,
            mode=mode.value,
            retrieval_strategy=strategy.value,
        )

        # KG visibility per mode: only HYBRID and KG_ONLY pass the graph downstream.
        kg_for_decomposer = (
            knowledge_graph
            if mode in (PredictionMode.HYBRID, PredictionMode.KG_ONLY)
            else None
        )

        # ── Step 1: Issue Decomposition (deterministic) ──
        issues = self.issue_decomposer.decompose(case_file, kg_for_decomposer)
        metadata.issues_decomposed = len(issues)
        metadata.steps_executed.append("issue_decomposition")

        if not issues:
            logger.info("prediction_v2_no_issues", case_id=case_file.case_id)
            return PredictionResult.create_uncertain(
                case_id=case_file.case_id,
                reason="No disputed issues identified in the case.",
            )

        logger.info(
            "issues_decomposed",
            case_id=case_file.case_id,
            count=len(issues),
            types=[i.issue_type.value for i in issues],
        )

        # Derive typed KG facts per issue (used by both retrieval reranker and
        # the prompt-side fact card). Empty when KG hidden by mode.
        kg_facts_by_issue: Dict[Any, KGFacts] = {}
        if (
            mode in (PredictionMode.HYBRID, PredictionMode.KG_ONLY)
            and knowledge_graph is not None
        ):
            for issue in issues:
                kg_facts_by_issue[issue.issue_type] = derive_kg_facts(
                    knowledge_graph, issue.issue_type
                )

        # Stream C PR 4 Task 4.5: build the per-issue case_graph map. For
        # housing.deposit.v1, the deposit pack's render_factor_card accepts
        # the legacy ``KGFacts`` adapter directly, so we reuse it. For
        # repairs (and future domains), the pack reads FactorAssertion
        # nodes off the full KnowledgeGraph. CaseFile may not carry a
        # domain_id on legacy fixtures — default to deposit in that case.
        case_graph_by_issue: Dict[Any, Any] = {}
        if knowledge_graph is not None and mode in (
            PredictionMode.HYBRID,
            PredictionMode.KG_ONLY,
        ):
            domain_id = getattr(case_file, "domain_id", None) or "housing.deposit.v1"
            for issue in issues:
                if domain_id == "housing.deposit.v1":
                    case_graph_by_issue[issue.issue_type] = kg_facts_by_issue.get(
                        issue.issue_type
                    )
                else:
                    case_graph_by_issue[issue.issue_type] = knowledge_graph

        # ── Modes that skip retrieval entirely (LLM_ONLY, KG_ONLY) ──
        if mode in (PredictionMode.LLM_ONLY, PredictionMode.KG_ONLY):
            self.issue_predictor._case_file = case_file
            self.issue_predictor._kg_facts_by_issue = kg_facts_by_issue
            self.issue_predictor._case_graph_by_issue = case_graph_by_issue
            prompt_mode = "llm_only" if mode == PredictionMode.LLM_ONLY else "kg_only"
            metadata.steps_executed.append(f"{prompt_mode}_path")
            issue_predictions = await self.issue_predictor.predict_no_rag(
                issues, prompt_mode=prompt_mode,
            )
            self._copy_kg_metadata_to_pipeline(metadata)
            metadata.total_llm_calls = sum(
                1 for ip in issue_predictions
                if ip.outcome != IssueOutcome.UNCERTAIN
            )
            metadata.total_latency_ms = int((time.time() - start_time) * 1000)
            metadata.steps_executed.append("output_assembly")
            return self.output_assembler.assemble(
                case_file=case_file,
                issues=issues,
                issue_predictions=issue_predictions,
                retrieval_results={},
                verification=CitationVerifier.empty_verification(),
                pipeline_metadata=metadata,
                matter_type=matter_type,
            )

        # ── Step 2: Per-Issue Retrieval (parallel retriever calls) ──
        needs_chunk_rag = strategy in (
            RetrievalStrategy.CHUNK_RAG,
            RetrievalStrategy.HYBRID_CHUNK_PROPOSITION,
        )
        needs_propositions = strategy in (
            RetrievalStrategy.PROPOSITION_DIRECT,
            RetrievalStrategy.PROPOSITION_PAGERANK,
            RetrievalStrategy.HYBRID_CHUNK_PROPOSITION,
        )
        if needs_chunk_rag and not self.rag and not (
            needs_propositions and self.proposition_retriever is not None
        ):
            return PredictionResult.create_uncertain(
                case_id=case_file.case_id,
                reason="RAG pipeline not available.",
            )
        if needs_propositions and self.proposition_retriever is None and not self.rag:
            return PredictionResult.create_uncertain(
                case_id=case_file.case_id,
                reason="Proposition retriever not available.",
            )

        if strategy == RetrievalStrategy.AGENTIC:
            retrieval_results = await self._agentic_retrieve_all(
                issues=issues,
                case_file=case_file,
                metadata=metadata,
            )
            metadata.steps_executed.append("agentic_retrieval")
        else:
            repairs_hybrid = self._uses_purposeful_repairs_retrieval(
                case_file,
                issues,
                mode,
                strategy,
            )
            if repairs_hybrid:
                metadata.steps_executed.append("retrieval_planning")
            retrieval_results = await self.issue_retriever.retrieve_all(
                issues, case_file, top_k,
                kg_facts_by_issue=kg_facts_by_issue,
                mode=mode,
                retrieval_strategy=strategy,
            )
            if repairs_hybrid:
                metadata.steps_executed.extend(
                    [
                        "liability_retrieval",
                        "remedy_retrieval",
                        "counterexample_retrieval",
                        "award_amount_retrieval",
                    ]
                )
            else:
                metadata.steps_executed.append("per_issue_retrieval")

        sufficient_count = sum(1 for r in retrieval_results.values() if r.is_sufficient)
        metadata.issues_with_sufficient_cases = sufficient_count

        logger.info(
            "retrieval_complete",
            case_id=case_file.case_id,
            total_issues=len(issues),
            sufficient=sufficient_count,
            retrieval_strategy=strategy.value,
        )

        if sufficient_count == 0:
            return PredictionResult.create_uncertain(
                case_id=case_file.case_id,
                reason="No sufficient similar cases found for any disputed issue.",
            )

        # ── Step 3: Per-Issue Prediction (parallel LLM calls) ──
        self.issue_predictor._case_file = case_file
        self.issue_predictor._kg_facts_by_issue = kg_facts_by_issue
        self.issue_predictor._case_graph_by_issue = case_graph_by_issue
        # Thread the prompt mode so the rag_only gate inside _predict_issue
        # actually fires in production (it short-circuits the factor card).
        prompt_mode_str = (
            "rag_only" if mode == PredictionMode.RAG_ONLY else "hybrid"
        )
        issue_predictions = await self.issue_predictor.predict_all(
            issues,
            retrieval_results,
            case_file=case_file,
            prompt_mode=prompt_mode_str,
        )
        # Surface KG gate metadata into the artifact (§17.6 / Cross-PR C5).
        # NOTE: ``_last_kg_metadata`` reflects the LAST issue's render, since
        # IssuePredictor mutates a single shared field. PR 5 may upgrade this
        # to per-issue metadata once factor extraction lands.
        self._copy_kg_metadata_to_pipeline(metadata)
        predicted_count = sum(
            1 for ip in issue_predictions if ip.outcome != IssueOutcome.UNCERTAIN
        )
        metadata.total_llm_calls = predicted_count
        metadata.steps_executed.append("per_issue_prediction")

        logger.info(
            "predictions_generated",
            case_id=case_file.case_id,
            predicted=predicted_count,
            uncertain=len(issue_predictions) - predicted_count,
        )

        # ── Step 5: Citation Verification (deterministic) ──
        issue_predictions, verification = self.citation_verifier.verify(
            issue_predictions, retrieval_results
        )
        metadata.steps_executed.append("citation_verification")

        logger.info(
            "citations_verified",
            case_id=case_file.case_id,
            removal_rate=verification.removal_rate,
            needs_reprediction=verification.needs_reprediction,
        )

        # ── Step 7: Output Assembly (deterministic) ──
        metadata.total_latency_ms = int((time.time() - start_time) * 1000)
        metadata.steps_executed.append("output_assembly")

        result = self.output_assembler.assemble(
            case_file=case_file,
            issues=issues,
            issue_predictions=issue_predictions,
            retrieval_results=retrieval_results,
            verification=verification,
            pipeline_metadata=metadata,
            matter_type=matter_type,
        )

        logger.info(
            "prediction_v2_complete",
            case_id=case_file.case_id,
            outcome=result.overall_outcome.value,
            confidence=result.overall_confidence,
            issues=len(result.issue_predictions),
            citations=result.get_citation_count(),
            latency_ms=metadata.total_latency_ms,
        )

        return result

    @staticmethod
    def _uses_purposeful_repairs_retrieval(
        case_file: CaseFile,
        issues: List[IssueContext],
        mode: PredictionMode,
        retrieval_strategy: RetrievalStrategy,
    ) -> bool:
        if (
            mode != PredictionMode.HYBRID
            or retrieval_strategy != RetrievalStrategy.CHUNK_RAG
        ):
            return False
        repairs_issue_values = {
            "repairs_disrepair",
            "repairs_damp_mould",
            "complaint_handling_failure",
        }
        if any(issue.issue_type.value in repairs_issue_values for issue in issues):
            return True
        metadata = getattr(case_file, "metadata", None)
        return isinstance(metadata, dict) and (
            metadata.get("domain_id") == "housing.repairs_social.v1"
        )

    async def _agentic_retrieve_all(
        self,
        *,
        issues: List[IssueContext],
        case_file: CaseFile,
        metadata: PipelineMetadata,
    ) -> Dict[IssueType, IssueRetrievalResult]:
        """Run the iterative retrieval agent once per issue.

        Each issue gets its own ``run_agent_loop`` call. The agent's
        curated chunks are converted into the existing
        ``IssueRetrievalResult`` shape so the downstream IRAC
        predictor consumes them unchanged. Per-issue agent traces
        are appended to ``metadata.agent_traces`` for the audit gate
        (plan §5.4).

        The leakage envelope is inherited automatically: ``self.rag``
        is whatever the engine was constructed with (typically a
        ``_EvalFilteredRAGPipeline``), and the agent's tools call
        ``rag.retrieve(...)`` on that same instance.
        """
        # Local imports keep prediction_engine_v2.py free of agent-only
        # deps when the AGENTIC strategy is never used.
        from .retrieval_agent_loop import run_agent_loop

        # Build a small case-summary string the planner can use. Keep
        # it short — the planner is paid per token. The case_file's
        # tenant_narrative + issue_description are the natural source.
        case_summary = self._build_planner_case_summary(case_file)
        gold_case_id = getattr(case_file, "case_id", "") or ""

        results: Dict[IssueType, IssueRetrievalResult] = {}
        for issue in issues:
            state = await run_agent_loop(
                llm_client=self.llm,
                rag=self.rag,
                case_summary=case_summary,
                issue_type=issue.issue_type.value,
                gold_case_id=gold_case_id,
                kg=None,  # check_kg_fact stub returns unknown — wired in F-KG-1
            )

            # Track tokens / fallbacks at the pipeline level.
            metadata.total_tokens_used += state.tokens_used
            metadata.agent_traces.append(self._serialise_agent_state(state))

            # Convert agent state into IssueRetrievalResult.
            result = _agent_state_to_retrieval_result(
                state=state, issue_type=issue.issue_type
            )
            results[issue.issue_type] = result

            logger.info(
                "agentic_retrieval_complete",
                case_id=case_file.case_id,
                issue=issue.issue_type.value,
                terminator=state.terminator,
                iter_count=state.iter,
                chunks=len(state.chunks_so_far),
                tokens=state.tokens_used,
            )

        return results

    @staticmethod
    def _build_planner_case_summary(case_file: CaseFile) -> str:
        """Render a short, plain-English case summary for the planner.

        Concatenates tenant_narrative + landlord_narrative + the first
        issue description. The planner already truncates input length
        on its end, but keeping it short here also limits tokens we
        pay for on a forced cache miss.
        """
        parts: List[str] = []
        for attr in ("tenant_narrative", "landlord_narrative"):
            text = getattr(case_file, attr, None)
            if text:
                parts.append(str(text).strip())
        # Issue description as a fallback if no narratives exist.
        if not parts:
            issues = getattr(case_file, "issues", []) or []
            for iss in issues:
                desc = getattr(iss, "description", "") or ""
                if desc:
                    parts.append(desc.strip())
        summary = "\n\n".join(parts)
        # Hard truncate at 2400 chars (~400 words). The planner system
        # prompt already says "case summary <=400 words"; this is the
        # belt-and-braces enforcement.
        return summary[:2400]

    def _copy_kg_metadata_to_pipeline(self, metadata: PipelineMetadata) -> None:
        """Copy ``IssuePredictor._last_kg_metadata`` into ``PipelineMetadata``.

        The §17.6 / Cross-PR Contract C5 fields (graph_quality_score,
        kg_used_for_prediction, kg_fallback_mode, kg_gate_failure_reasons)
        are populated by ``_render_factor_card_via_pack`` (and the rag_only
        short-circuit) per issue. Because the predictor mutates a single
        shared field, this captures the LAST issue's render only — fine for
        single-issue deposit cases, and acceptable for PR 4 multi-issue
        cases since all issues route through the same domain pack and gate.
        PR 5 may upgrade to per-issue metadata.
        """
        last = getattr(self.issue_predictor, "_last_kg_metadata", None) or {}
        if not last:
            return
        metadata.graph_quality_score = last.get("graph_quality_score")
        metadata.kg_used_for_prediction = last.get("kg_used_for_prediction")
        metadata.kg_fallback_mode = last.get("kg_fallback_mode")
        metadata.kg_gate_failure_reasons = list(
            last.get("kg_gate_failure_reasons") or []
        )

    @staticmethod
    def _serialise_agent_state(state: Any) -> Dict[str, Any]:
        """Compact, JSON-friendly view of one agent loop's state for
        the trace artifact. Heavy chunk text is dropped — only the IDs
        survive, since the chunks themselves are already represented
        in retrieval_results."""
        return {
            "case_id": state.case_id,
            "issue_type": state.issue_type,
            "iter_count": state.iter,
            "terminator": state.terminator,
            "tokens_used": state.tokens_used,
            "queries_so_far": [
                {"purpose": p, "query": q} for p, q in state.queries_so_far
            ],
            "chunks_count": len(state.chunks_so_far),
            "chunk_ids": [c.chunk_id for c in state.chunks_so_far],
            "amounts_extracted_count": len(state.amounts_extracted),
            "kg_facts_seen": [
                {"field": f.field, "is_known": f.is_known}
                for f in state.kg_facts_seen
            ],
            "blocked_queries": list(state.blocked_queries),
            "judge_log": [
                {
                    "tool": a.tool,
                    "input": a.input,
                    "confidence_score": a.confidence_score,
                }
                for a in state.judge_log
            ],
            "leakage_audit": {
                "all_queries_filter_applied": True,
                "blocked_queries_count": len(state.blocked_queries),
            },
        }


def _agent_state_to_retrieval_result(
    *, state: Any, issue_type: IssueType
) -> IssueRetrievalResult:
    """Convert an ``AgentState`` into the engine's
    ``IssueRetrievalResult`` so the IRAC predictor consumes the
    agent's curated chunks unchanged.

    The predictor (``issue_predictor.py:359-376``) accesses fields
    via ``self._get_value`` which works against either a dict or an
    object. We emit dicts with both the new (``chunk_id``,
    ``source_id``, ``section_type``) and legacy (``case_reference``,
    ``chunk_text``, ``combined_score``) keys so the predictor sees
    everything it expects without changes.
    """
    JUDGE_TERMINATORS = {"judge_ok", "judge_abstain"}
    is_sufficient = (
        bool(state.chunks_so_far)
        and state.terminator in JUDGE_TERMINATORS
    )
    query_used = " | ".join(
        f"[{p}] {q}" for p, q in state.queries_so_far
    )

    converted: List[Dict[str, Any]] = []
    for c in state.chunks_so_far:
        converted.append(
            {
                # Native AgentChunk shape
                "chunk_id": c.chunk_id,
                "source_id": c.source_id,
                "paragraph_id": c.paragraph_id,
                "section_type": c.section_type,
                "score": c.score,
                "purpose": c.purpose,
                # Legacy predictor-shape keys (issue_predictor.py
                # accesses these via _get_value with safe defaults)
                "case_reference": c.source_id,
                "chunk_text": c.text,
                "text": c.text,
                "combined_score": c.score,
                "year": "N/A",  # AgentChunk has no year; predictor falls back
            }
        )

    return IssueRetrievalResult(
        issue_type=issue_type,
        query_used=query_used,
        results=converted,
        rag_confidence=0.5 if is_sufficient else 0.0,
        is_sufficient=is_sufficient,
    )
