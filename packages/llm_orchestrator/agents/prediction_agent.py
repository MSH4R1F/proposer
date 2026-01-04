"""
Prediction engine for outcome prediction.

Combines RAG retrieval with LLM synthesis to generate
case outcome predictions with reasoning traces.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

from ..clients.base import BaseLLMClient
from ..models.case_file import CaseFile, PartyRole
from ..models.prediction import (
    PredictionResult,
    OutcomeType,
    IssuePrediction,
    ReasoningStep,
    Citation,
)
from ..prompts.prediction import (
    PREDICTION_SYSTEM_PROMPT,
    PREDICTION_USER_PROMPT,
    PREDICTION_JSON_SCHEMA,
    INSUFFICIENT_EVIDENCE_PROMPT,
)

logger = structlog.get_logger()


class PredictionEngine:
    """
    Prediction engine combining RAG retrieval + LLM synthesis.

    Implements the cite-or-abstain rule: every factual claim
    must be backed by a retrieved case citation.
    """

    def __init__(
        self,
        llm_client: BaseLLMClient,
        rag_pipeline: Optional[Any] = None,
        min_confidence: float = 0.5,
        min_cases_required: int = 3,
    ):
        """
        Initialize the prediction engine.

        Args:
            llm_client: LLM client for synthesis
            rag_pipeline: RAG pipeline for case retrieval (optional)
            min_confidence: Minimum RAG confidence to proceed
            min_cases_required: Minimum similar cases needed
        """
        self.llm = llm_client
        self.rag = rag_pipeline
        self.min_confidence = min_confidence
        self.min_cases_required = min_cases_required

    def set_rag_pipeline(self, rag_pipeline: Any) -> None:
        """Set the RAG pipeline after initialization."""
        self.rag = rag_pipeline

    async def predict(
        self,
        case_file: CaseFile,
        knowledge_graph: Optional[Any] = None,
        top_k: int = 10,
    ) -> PredictionResult:
        """
        Generate outcome prediction with reasoning trace.

        Args:
            case_file: Complete case file from intake
            knowledge_graph: Optional KG for enhanced context
            top_k: Number of similar cases to retrieve

        Returns:
            PredictionResult with cited reasoning
        """
        # Step 1: Build query from case file
        query = self._build_query(case_file)

        logger.info(
            "prediction_starting",
            case_id=case_file.case_id,
            query_preview=query[:100],
        )

        # Step 2: Retrieve similar cases (if RAG available)
        rag_result = None
        if self.rag:
            try:
                rag_result = await self.rag.retrieve(
                    query=query,
                    top_k=top_k,
                    query_region=case_file.property.region,
                )
            except Exception as e:
                logger.error("rag_retrieval_failed", error=str(e))

        # Step 3: Check confidence - cite-or-abstain
        if rag_result:
            if rag_result.is_uncertain or rag_result.confidence < self.min_confidence:
                logger.info(
                    "cite_or_abstain_triggered",
                    reason=rag_result.uncertainty_reason or "Low confidence",
                    confidence=rag_result.confidence,
                )
                return self._create_uncertain_prediction(
                    case_file,
                    rag_result.uncertainty_reason or "Insufficient similar cases found",
                )

            if len(rag_result.results) < self.min_cases_required:
                return self._create_uncertain_prediction(
                    case_file,
                    f"Only {len(rag_result.results)} similar cases found (minimum {self.min_cases_required} required)",
                )

        # Step 4: Synthesize prediction with LLM
        prediction = await self._synthesize_prediction(
            case_file,
            rag_result,
            knowledge_graph,
        )

        logger.info(
            "prediction_generated",
            case_id=case_file.case_id,
            outcome=prediction.overall_outcome.value,
            confidence=prediction.overall_confidence,
            citations=prediction.get_citation_count(),
        )

        return prediction

    def _build_query(self, case_file: CaseFile) -> str:
        """Build a search query from case file."""
        return case_file.to_query_string()

    async def _synthesize_prediction(
        self,
        case_file: CaseFile,
        rag_result: Optional[Any],
        knowledge_graph: Optional[Any],
    ) -> PredictionResult:
        """Use LLM to synthesize prediction from case + precedents."""

        # Format retrieved cases for context
        if rag_result:
            context = self._format_precedents(rag_result.results)
            rag_confidence = rag_result.confidence
            retrieved_cases = [r.case_reference for r in rag_result.results]
        else:
            context = "No similar cases retrieved. Generate prediction based on general legal principles only."
            rag_confidence = 0.0
            retrieved_cases = []

        # Format case facts
        case_facts = self._format_case_facts(case_file)

        # Format KG summary
        kg_summary = self._format_kg_summary(knowledge_graph) if knowledge_graph else "No knowledge graph available."

        # Build the user prompt
        user_prompt = PREDICTION_USER_PROMPT.format(
            retrieved_cases=context,
            case_facts=case_facts,
            kg_summary=kg_summary,
        )

        # Full system prompt with JSON schema
        system_prompt = f"{PREDICTION_SYSTEM_PROMPT}\n\n{PREDICTION_JSON_SCHEMA}"

        # Generate prediction
        response = await self.llm.generate(
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=system_prompt,
            max_tokens=4096,
            temperature=0.3,  # Lower temp for more consistent predictions
        )

        # Parse response into PredictionResult
        prediction = self._parse_prediction_response(
            response,
            case_file,
            rag_confidence,
            retrieved_cases,
        )

        return prediction

    def _format_precedents(self, results: List[Any]) -> str:
        """Format retrieved cases for LLM context."""
        formatted = []

        for i, r in enumerate(results, 1):
            # Handle both dict-like and object access
            if hasattr(r, "case_reference"):
                case_ref = r.case_reference
                year = r.year
                section_type = getattr(r, "section_type", "unknown")
                combined_score = getattr(r, "combined_score", 0)
                relevance = getattr(r, "relevance_explanation", "")
                text = getattr(r, "chunk_text", getattr(r, "text", ""))
            else:
                case_ref = r.get("case_reference", "Unknown")
                year = r.get("year", "N/A")
                section_type = r.get("section_type", "unknown")
                combined_score = r.get("combined_score", 0)
                relevance = r.get("relevance_explanation", "")
                text = r.get("chunk_text", r.get("text", ""))

            formatted.append(f"""
CASE {i}: {case_ref} ({year})
Section: {section_type}
Relevance Score: {combined_score:.3f}
{relevance}

Text:
{text[:1500]}...
---
""")

        return "\n".join(formatted)

    def _format_case_facts(self, case_file: CaseFile) -> str:
        """Format case file facts for LLM context."""
        lines = [
            f"User Role: {case_file.user_role.value}",
            f"Property: {case_file.property.address or 'Not specified'}",
            f"Region: {case_file.property.region or 'Unknown'}",
        ]

        if case_file.tenancy.start_date:
            lines.append(f"Tenancy Start: {case_file.tenancy.start_date}")
        if case_file.tenancy.end_date:
            lines.append(f"Tenancy End: {case_file.tenancy.end_date}")
        if case_file.tenancy.monthly_rent:
            lines.append(f"Monthly Rent: £{case_file.tenancy.monthly_rent}")

        lines.append(f"Deposit Amount: £{case_file.tenancy.deposit_amount or 'Unknown'}")

        if case_file.tenancy.deposit_protected is not None:
            status = "Protected" if case_file.tenancy.deposit_protected else "NOT PROTECTED"
            lines.append(f"Deposit Protection: {status}")
            if case_file.tenancy.deposit_scheme:
                lines.append(f"Deposit Scheme: {case_file.tenancy.deposit_scheme}")

        if case_file.issues:
            lines.append(f"\nDisputed Issues:")
            for issue in case_file.issues:
                lines.append(f"  - {issue.value}")

        if case_file.tenant_claims:
            lines.append(f"\nTenant Claims:")
            for claim in case_file.tenant_claims:
                lines.append(f"  - {claim.issue.value}: £{claim.amount} - {claim.description}")

        if case_file.landlord_claims:
            lines.append(f"\nLandlord Claims:")
            for claim in case_file.landlord_claims:
                lines.append(f"  - {claim.issue.value}: £{claim.amount} - {claim.description}")

        if case_file.evidence:
            lines.append(f"\nEvidence Available:")
            for ev in case_file.evidence:
                lines.append(f"  - {ev.type.value}: {ev.description}")

        narrative = case_file.tenant_narrative or case_file.landlord_narrative
        if narrative:
            lines.append(f"\nNarrative:\n{narrative[:500]}")

        return "\n".join(lines)

    def _format_kg_summary(self, kg: Any) -> str:
        """Format knowledge graph summary for context."""
        if hasattr(kg, "to_summary"):
            summary = kg.to_summary()
            lines = [
                f"Nodes: {summary.get('node_count', 0)}",
                f"Edges: {summary.get('edge_count', 0)}",
                f"Consistent: {summary.get('is_consistent', True)}",
            ]
            if summary.get("validation_warnings"):
                lines.append(f"Warnings: {summary['validation_warnings']}")
            return "\n".join(lines)

        return "Knowledge graph summary not available."

    def _parse_prediction_response(
        self,
        response: str,
        case_file: CaseFile,
        rag_confidence: float,
        retrieved_cases: List[str],
    ) -> PredictionResult:
        """Parse LLM response into PredictionResult."""
        try:
            # Try to extract JSON from response
            response = response.strip()

            # Handle markdown code blocks
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                response = response[start:end].strip()
            elif "```" in response:
                start = response.find("```") + 3
                end = response.find("```", start)
                response = response[start:end].strip()

            data = json.loads(response)

            # Parse outcome
            outcome_str = data.get("overall_outcome", "uncertain").lower()
            try:
                outcome = OutcomeType(outcome_str)
            except ValueError:
                outcome = OutcomeType.UNCERTAIN

            # Parse issue predictions
            issue_preds = []
            for ip in data.get("issue_predictions", []):
                try:
                    pred_outcome = OutcomeType(ip.get("predicted_outcome", "uncertain").lower())
                except ValueError:
                    pred_outcome = OutcomeType.UNCERTAIN

                citations = [
                    Citation(
                        case_reference=c.get("case_reference", ""),
                        year=c.get("year", 2022),
                        quote=c.get("quote", ""),
                        relevance=c.get("relevance", ""),
                    )
                    for c in ip.get("supporting_cases", [])
                ]

                issue_preds.append(IssuePrediction(
                    issue_type=ip.get("issue_type", ""),
                    issue_description=ip.get("issue_type", ""),
                    predicted_outcome=pred_outcome,
                    predicted_amount=ip.get("predicted_amount"),
                    confidence=ip.get("confidence", 0.5),
                    reasoning=ip.get("reasoning", ""),
                    key_factors=ip.get("key_factors", []),
                    supporting_cases=citations,
                ))

            # Parse reasoning trace
            reasoning = []
            for step in data.get("reasoning_trace", []):
                citations = [
                    Citation(
                        case_reference=c.get("case_reference", ""),
                        year=c.get("year", 2022),
                        quote=c.get("quote", ""),
                        relevance=c.get("relevance", ""),
                    )
                    for c in step.get("citations", [])
                ]

                reasoning.append(ReasoningStep(
                    step_number=step.get("step_number", len(reasoning) + 1),
                    category=step.get("category", "analysis"),
                    title=step.get("title", ""),
                    content=step.get("content", ""),
                    citations=citations,
                    confidence=step.get("confidence", 0.7),
                ))

            # Parse settlement range
            settlement_range = data.get("predicted_settlement_range")
            if settlement_range and len(settlement_range) == 2:
                settlement_range = tuple(settlement_range)
            else:
                settlement_range = None

            return PredictionResult(
                case_id=case_file.case_id,
                overall_outcome=outcome,
                overall_confidence=data.get("overall_confidence", 0.5),
                outcome_summary=data.get("outcome_summary", ""),
                tenant_recovery_amount=data.get("tenant_recovery_amount"),
                landlord_recovery_amount=data.get("landlord_recovery_amount"),
                predicted_settlement_range=settlement_range,
                deposit_at_stake=case_file.tenancy.deposit_amount,
                issue_predictions=issue_preds,
                reasoning_trace=reasoning,
                key_strengths=data.get("key_strengths", []),
                key_weaknesses=data.get("key_weaknesses", []),
                uncertainties=data.get("uncertainties", []),
                missing_information=data.get("missing_information", []),
                assumptions_made=data.get("assumptions_made", []),
                retrieved_cases=retrieved_cases,
                total_cases_analyzed=len(retrieved_cases),
                rag_confidence=rag_confidence,
            )

        except json.JSONDecodeError as e:
            logger.error("prediction_json_parse_error", error=str(e))
            return self._create_fallback_prediction(case_file, response)

        except Exception as e:
            logger.error("prediction_parse_error", error=str(e))
            return self._create_fallback_prediction(case_file, response)

    def _create_uncertain_prediction(
        self,
        case_file: CaseFile,
        reason: str,
    ) -> PredictionResult:
        """Create an uncertain prediction when cite-or-abstain triggers."""
        return PredictionResult.create_uncertain(
            case_id=case_file.case_id,
            reason=reason,
            missing_info=case_file.missing_info,
        )

    def _create_fallback_prediction(
        self,
        case_file: CaseFile,
        raw_response: str,
    ) -> PredictionResult:
        """Create a fallback prediction when parsing fails."""
        return PredictionResult(
            case_id=case_file.case_id,
            overall_outcome=OutcomeType.UNCERTAIN,
            overall_confidence=0.3,
            outcome_summary="Unable to parse structured prediction. See reasoning trace for analysis.",
            reasoning_trace=[
                ReasoningStep(
                    step_number=1,
                    category="analysis",
                    title="Raw Analysis",
                    content=raw_response[:2000],
                    citations=[],
                    confidence=0.3,
                )
            ],
            uncertainties=["Failed to parse structured prediction format"],
            retrieval_quality="poor",
        )
