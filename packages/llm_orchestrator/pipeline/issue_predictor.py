import asyncio
import importlib
import json
import structlog
from typing import Any, Dict, List, Optional

from ..clients.base import BaseLLMClient
from ..models.prediction_v2 import (
    Citation,
    EvidenceStrength,
    IssueContext,
    IssueOutcome,
    IssuePrediction,
    IssueRetrievalResult,
    IssueType,
)

_prediction_v2_prompts = importlib.import_module(
    "llm_orchestrator.prompts.prediction_v2"
)
IRAC_JSON_SCHEMA = getattr(_prediction_v2_prompts, "IRAC_JSON_SCHEMA")
IRAC_SYSTEM_PROMPT = getattr(_prediction_v2_prompts, "IRAC_SYSTEM_PROMPT")
IRAC_USER_PROMPT = getattr(_prediction_v2_prompts, "IRAC_USER_PROMPT")

logger = structlog.get_logger()


class IssuePredictor:
    def __init__(self, llm_client: BaseLLMClient):
        self.llm = llm_client

    async def predict_all(
        self,
        issues: List[IssueContext],
        retrieval_results: Dict[IssueType, IssueRetrievalResult],
    ) -> List[IssuePrediction]:
        sufficient_issues: List[IssueContext] = []
        uncertain_by_issue: Dict[IssueType, IssuePrediction] = {}

        for issue in issues:
            retrieval = retrieval_results.get(issue.issue_type)
            if retrieval and retrieval.is_sufficient:
                sufficient_issues.append(issue)
                continue

            uncertain_by_issue[issue.issue_type] = IssuePrediction(
                issue_type=issue.issue_type,
                issue_description=issue.issue_description,
                outcome=IssueOutcome.UNCERTAIN,
                raw_confidence=0.0,
                reasoning="Insufficient similar cases found for this issue.",
                evidence_strength=EvidenceStrength.INSUFFICIENT,
                data_completeness_impact="Cannot predict due to lack of precedent cases.",
            )

        if sufficient_issues:
            llm_results = await asyncio.gather(
                *[
                    self._predict_issue(issue, retrieval_results[issue.issue_type])
                    for issue in sufficient_issues
                ],
                return_exceptions=True,
            )
            for issue, result in zip(sufficient_issues, llm_results):
                if isinstance(result, Exception):
                    logger.error(
                        "issue_prediction_failed",
                        issue_type=issue.issue_type.value,
                        error=str(result),
                    )
                    uncertain_by_issue[issue.issue_type] = self._uncertain_prediction(
                        issue=issue,
                        reason="LLM prediction failed for this issue.",
                        evidence_strength=self._assess_evidence_strength(issue),
                        data_impact="Prediction failed due to model/runtime error.",
                    )
                elif isinstance(result, IssuePrediction):
                    uncertain_by_issue[issue.issue_type] = result
                else:
                    uncertain_by_issue[issue.issue_type] = self._uncertain_prediction(
                        issue=issue,
                        reason="Unexpected prediction result type.",
                        evidence_strength=self._assess_evidence_strength(issue),
                        data_impact="Issue prediction failed type validation.",
                    )

        return [
            uncertain_by_issue.get(issue.issue_type)
            or self._uncertain_prediction(
                issue=issue,
                reason="Issue prediction unavailable.",
                evidence_strength=self._assess_evidence_strength(issue),
                data_impact="Issue could not be processed.",
            )
            for issue in issues
        ]

    async def _predict_issue(
        self,
        issue: IssueContext,
        retrieval: IssueRetrievalResult,
    ) -> IssuePrediction:
        formatted_cases = []
        for i, result in enumerate(retrieval.results[:8], 1):
            case_ref = self._get_value(result, "case_reference", "Unknown")
            year = self._get_value(result, "year", "N/A")
            text = self._get_value(
                result,
                "chunk_text",
                self._get_value(result, "text", ""),
            )
            score = self._to_float(
                self._get_value(
                    result,
                    "combined_score",
                    self._get_value(result, "rerank_score", 0),
                )
            )
            formatted_cases.append(
                f"CASE {i}: {case_ref} ({year})\nRelevance: {score:.3f}\n{str(text)[:1500]}\n---"
            )
        retrieved_cases_str = "\n".join(formatted_cases)

        evidence_summary = self._format_evidence_summary(issue)
        claimed_amount = issue.claimed_amount
        if claimed_amount is None:
            claimed_amount = (
                issue.landlord_claim.claimed_amount
                if issue.landlord_claim
                and issue.landlord_claim.claimed_amount is not None
                else issue.tenant_claim.claimed_amount
                if issue.tenant_claim and issue.tenant_claim.claimed_amount is not None
                else None
            )

        prompt_kwargs = {
            "issue_type": issue.issue_type.value,
            "issue_description": issue.issue_description,
            "claimed_amount": claimed_amount
            if claimed_amount is not None
            else "unknown",
            "data_completeness": issue.data_completeness,
            "kg_constraints": "\n".join(issue.kg_constraints) or "None provided",
            "evidence_summary": evidence_summary,
            "retrieved_cases": retrieved_cases_str,
            "tenant_claim": issue.tenant_claim.description
            if issue.tenant_claim
            else "",
            "landlord_claim": issue.landlord_claim.description
            if issue.landlord_claim
            else "",
        }
        try:
            user_prompt = IRAC_USER_PROMPT.format(**prompt_kwargs)
        except Exception:
            user_prompt = (
                f"Issue Type: {issue.issue_type.value}\n"
                f"Issue Description: {issue.issue_description}\n"
                f"Claimed Amount: {prompt_kwargs['claimed_amount']}\n"
                f"Data Completeness: {issue.data_completeness:.2f}\n"
                f"Tenant Claim: {prompt_kwargs['tenant_claim']}\n"
                f"Landlord Claim: {prompt_kwargs['landlord_claim']}\n"
                f"KG Constraints:\n{prompt_kwargs['kg_constraints']}\n\n"
                f"Evidence Summary:\n{evidence_summary}\n\n"
                f"Retrieved Cases:\n{retrieved_cases_str}\n"
            )

        system_prompt = f"{IRAC_SYSTEM_PROMPT}\n\n{IRAC_JSON_SCHEMA}"

        attempts = 2
        last_response: Optional[str] = None
        for attempt in range(1, attempts + 1):
            try:
                response = await self.llm.generate(
                    messages=[{"role": "user", "content": user_prompt}],
                    system_prompt=system_prompt,
                    max_tokens=2000,
                    temperature=0.2,
                )
                last_response = response
                prediction = self._parse_prediction_response(response, issue)
                should_retry_parse = (
                    prediction.outcome == IssueOutcome.UNCERTAIN
                    and prediction.data_completeness_impact == "parse_error"
                    and attempt < attempts
                )
                if should_retry_parse:
                    logger.warning(
                        "issue_prediction_parse_retry",
                        issue_type=issue.issue_type.value,
                        attempt=attempt,
                    )
                    continue

                if prediction.outcome != IssueOutcome.UNCERTAIN or attempt == attempts:
                    prediction.issue_type = issue.issue_type
                    if not prediction.issue_description:
                        prediction.issue_description = issue.issue_description
                    if prediction.evidence_strength == EvidenceStrength.INSUFFICIENT:
                        prediction.evidence_strength = self._assess_evidence_strength(
                            issue
                        )
                    return prediction
            except Exception as exc:
                logger.error(
                    "issue_prediction_llm_error",
                    issue_type=issue.issue_type.value,
                    attempt=attempt,
                    error=str(exc),
                )

        return self._uncertain_prediction(
            issue=issue,
            reason="Could not parse model output for this issue.",
            evidence_strength=self._assess_evidence_strength(issue),
            data_impact=(
                "Prediction fell back to uncertain after parsing/model failure."
                if last_response
                else "Prediction failed due to unavailable model response."
            ),
        )

    def _parse_prediction_response(
        self,
        response: str,
        issue: IssueContext,
    ) -> IssuePrediction:
        try:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.splitlines()
                if len(lines) >= 2:
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                cleaned = "\n".join(lines).strip()

            if "```json" in cleaned:
                start = cleaned.find("```json") + len("```json")
                end = cleaned.find("```", start)
                cleaned = cleaned[start : end if end != -1 else None].strip()
            elif "```" in cleaned:
                start = cleaned.find("```") + len("```")
                end = cleaned.find("```", start)
                cleaned = cleaned[start : end if end != -1 else None].strip()

            data = json.loads(cleaned)

            outcome_raw = str(
                data.get("outcome", data.get("predicted_outcome", "uncertain"))
            ).lower()
            outcome_map = {
                "tenant_win": "tenant_wins",
                "landlord_win": "landlord_wins",
            }
            outcome_normalized = outcome_map.get(outcome_raw, outcome_raw)
            try:
                outcome = IssueOutcome(outcome_normalized)
            except ValueError:
                outcome = IssueOutcome.UNCERTAIN

            strength_raw = str(
                data.get(
                    "evidence_strength", self._assess_evidence_strength(issue).value
                )
            ).lower()
            try:
                evidence_strength = EvidenceStrength(strength_raw)
            except ValueError:
                evidence_strength = self._assess_evidence_strength(issue)

            citations_raw = data.get("supporting_cases", data.get("citations", []))
            citations: List[Citation] = []
            if isinstance(citations_raw, list):
                for citation in citations_raw:
                    if not isinstance(citation, dict):
                        continue
                    year = self._to_int(citation.get("year"), 2024)
                    citations.append(
                        Citation(
                            case_reference=str(
                                citation.get("case_reference", "Unknown")
                            ),
                            year=year if year is not None else 2024,
                            region=self._to_optional_str(citation.get("region")),
                            paragraph=self._to_optional_str(citation.get("paragraph")),
                            quote=str(citation.get("quote", "")),
                            relevance=str(citation.get("relevance", "")),
                            similarity_score=self._to_probability(
                                citation.get("similarity_score", 0.0)
                            ),
                            verified=bool(citation.get("verified", False)),
                        )
                    )

            key_factors_raw = data.get("key_factors", [])
            key_factors = (
                [str(item) for item in key_factors_raw]
                if isinstance(key_factors_raw, list)
                else []
            )

            predicted_amount = data.get("predicted_amount")
            amount_value = (
                self._to_float(predicted_amount)
                if predicted_amount is not None
                else issue.claimed_amount
            )

            return IssuePrediction(
                issue_type=issue.issue_type,
                issue_description=str(
                    data.get("issue_description", issue.issue_description)
                ),
                outcome=outcome,
                raw_confidence=self._to_probability(
                    data.get("raw_confidence", data.get("confidence", 0.0))
                ),
                predicted_amount=amount_value,
                reasoning=str(data.get("reasoning", "")).strip(),
                key_factors=key_factors,
                supporting_cases=citations,
                evidence_strength=evidence_strength,
                data_completeness_impact=str(
                    data.get(
                        "data_completeness_impact",
                        f"Issue data completeness is {issue.data_completeness:.2f}.",
                    )
                ),
            )
        except Exception as exc:
            logger.warning(
                "issue_prediction_parse_error",
                issue_type=issue.issue_type.value,
                error=str(exc),
            )
            return IssuePrediction(
                issue_type=issue.issue_type,
                issue_description=issue.issue_description,
                outcome=IssueOutcome.UNCERTAIN,
                raw_confidence=0.0,
                reasoning="Unable to parse model response for this issue.",
                evidence_strength=self._assess_evidence_strength(issue),
                data_completeness_impact="parse_error",
            )

    def _assess_evidence_strength(self, issue: IssueContext) -> EvidenceStrength:
        if issue.data_completeness >= 0.8:
            return EvidenceStrength.STRONG
        if issue.data_completeness >= 0.5:
            return EvidenceStrength.MODERATE
        if issue.data_completeness >= 0.2:
            return EvidenceStrength.WEAK
        return EvidenceStrength.INSUFFICIENT

    def _uncertain_prediction(
        self,
        issue: IssueContext,
        reason: str,
        evidence_strength: EvidenceStrength,
        data_impact: str,
    ) -> IssuePrediction:
        return IssuePrediction(
            issue_type=issue.issue_type,
            issue_description=issue.issue_description,
            outcome=IssueOutcome.UNCERTAIN,
            raw_confidence=0.0,
            reasoning=reason,
            evidence_strength=evidence_strength,
            data_completeness_impact=data_impact,
        )

    def _format_evidence_summary(self, issue: IssueContext) -> str:
        if not issue.supporting_evidence:
            return "No supporting evidence provided."

        rows: List[str] = []
        for idx, evidence in enumerate(issue.supporting_evidence, 1):
            if isinstance(evidence, dict):
                ev_type = (
                    evidence.get("type") or evidence.get("evidence_type") or "unknown"
                )
                description = evidence.get("description") or evidence.get("text") or ""
                confidence = evidence.get("confidence")
            else:
                ev_type_raw = getattr(
                    evidence, "type", getattr(evidence, "evidence_type", "unknown")
                )
                ev_type = str(getattr(ev_type_raw, "value", ev_type_raw))
                description = getattr(
                    evidence, "description", getattr(evidence, "text", "")
                )
                confidence = getattr(evidence, "confidence", None)

            conf_text = ""
            if confidence is not None:
                conf_text = f" (confidence={self._to_probability(confidence):.2f})"
            rows.append(f"{idx}. [{ev_type}] {str(description)[:300]}{conf_text}")

        return "\n".join(rows)

    @staticmethod
    def _get_value(obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _to_int(value: Any, default: Optional[int] = None) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_probability(value: Any) -> float:
        numeric = IssuePredictor._to_float(value)
        return max(0.0, min(1.0, numeric))

    @staticmethod
    def _to_optional_str(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text if text else None
