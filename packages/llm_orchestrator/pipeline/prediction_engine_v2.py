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
    IssueOutcome,
    PipelineMetadata,
    PredictionMode,
    PredictionResult,
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
    ):
        self.llm = llm_client
        self.rag = rag_pipeline
        self.min_confidence = min_confidence
        self.min_cases_required = min_cases_required

        self.issue_decomposer = IssueDecomposer()
        self.issue_retriever = IssueRetriever(rag_pipeline, min_cases_required)
        self.issue_predictor = IssuePredictor(llm_client)
        self.citation_verifier = CitationVerifier()
        self.output_assembler = OutputAssembler()

    def set_rag_pipeline(self, rag_pipeline: Any) -> None:
        self.rag = rag_pipeline
        self.issue_retriever = IssueRetriever(rag_pipeline, self.min_cases_required)

    async def predict(
        self,
        case_file: CaseFile,
        knowledge_graph: Optional[Any] = None,
        top_k: int = 10,
        mode: PredictionMode = PredictionMode.HYBRID,
    ) -> PredictionResult:
        start_time = time.time()
        metadata = PipelineMetadata(mode=mode.value)

        logger.info(
            "prediction_v2_starting",
            case_id=case_file.case_id,
            mode=mode.value,
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

        # ── Modes that skip retrieval entirely (LLM_ONLY, KG_ONLY) ──
        if mode in (PredictionMode.LLM_ONLY, PredictionMode.KG_ONLY):
            self.issue_predictor._case_file = case_file
            self.issue_predictor._kg_facts_by_issue = kg_facts_by_issue
            prompt_mode = "llm_only" if mode == PredictionMode.LLM_ONLY else "kg_only"
            metadata.steps_executed.append(f"{prompt_mode}_path")
            issue_predictions = await self.issue_predictor.predict_no_rag(
                issues, prompt_mode=prompt_mode,
            )
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
            )

        # ── Step 2: Per-Issue Retrieval (parallel RAG calls) ──
        if not self.rag:
            return PredictionResult.create_uncertain(
                case_id=case_file.case_id,
                reason="RAG pipeline not available.",
            )

        retrieval_results = await self.issue_retriever.retrieve_all(
            issues, case_file, top_k,
            kg_facts_by_issue=kg_facts_by_issue,
            mode=mode,
        )
        sufficient_count = sum(1 for r in retrieval_results.values() if r.is_sufficient)
        metadata.issues_with_sufficient_cases = sufficient_count
        metadata.steps_executed.append("per_issue_retrieval")

        logger.info(
            "retrieval_complete",
            case_id=case_file.case_id,
            total_issues=len(issues),
            sufficient=sufficient_count,
        )

        if sufficient_count == 0:
            return PredictionResult.create_uncertain(
                case_id=case_file.case_id,
                reason="No sufficient similar cases found for any disputed issue.",
            )

        # ── Step 3: Per-Issue Prediction (parallel LLM calls) ──
        self.issue_predictor._case_file = case_file
        self.issue_predictor._kg_facts_by_issue = kg_facts_by_issue
        issue_predictions = await self.issue_predictor.predict_all(
            issues, retrieval_results, case_file=case_file
        )
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
