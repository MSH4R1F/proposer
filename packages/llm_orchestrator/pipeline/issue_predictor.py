import asyncio
import importlib
import json
import math
import re
import structlog
from datetime import date as _date_type
from typing import Any, Dict, List, Optional

from ..clients.base import BaseLLMClient
from ..data.citation_urls import resolve_source_url
from ..models.prediction_v2 import (
    Citation,
    Determination,
    EvidenceStrength,
    IssueContext,
    IssueOutcome,
    IssuePrediction,
    IssueRetrievalResult,
    IssueType,
)
from ..prompts.prediction_v2 import (
    IRAC_JSON_SCHEMA,
    IRAC_SYSTEM_PROMPT,
    IRAC_USER_PROMPT,
)

_llm_only_prompts = importlib.import_module("llm_orchestrator.prompts.llm_only")
LLM_ONLY_SYSTEM_PROMPT = getattr(_llm_only_prompts, "LLM_ONLY_SYSTEM_PROMPT")
LLM_ONLY_USER_PROMPT = getattr(_llm_only_prompts, "LLM_ONLY_USER_PROMPT")

# Optional import for CaseFile — used for richer context if available
try:
    from ..models.case_file import CaseFile as _CaseFile
except ImportError:
    _CaseFile = None

logger = structlog.get_logger()

_REPAIRS_ISSUE_VALUES = {
    "repairs_disrepair",
    "repairs_damp_mould",
    "complaint_handling_failure",
}


_REPAIRS_NO_RAG_SYSTEM_PROMPT = """You analyse social-housing complaints heard by the Housing Ombudsman.

This is an ablation baseline with NO retrieved Ombudsman determinations. Predict from the resident/landlord facts, evidence summary, timeline, and any structured fact card only.

Critical constraints:
1. Do NOT invent Ombudsman determination citations. Leave supporting_cases as an empty list.
2. Do NOT mark the outcome uncertain solely because retrieved determinations are absent.
3. Use Housing Ombudsman concepts in the reasoning: no maladministration, service failure, maladministration, severe maladministration, reasonable redress, apology, repair action, compensation, case review, or policy review.
4. The JSON outcome field must still use the shared eval labels:
   - "tenant_wins" when the resident complaint is likely upheld on any substantive repairs/complaint-handling issue, or the landlord likely faces a service-failure/maladministration finding or additional remedy. Use this even if some complaint heads are not upheld.
   - "landlord_wins" when no maladministration/no service failure is likely.
   - "split" only when the likely result is genuinely balanced after remedies, with material findings for both sides and no clear resident-upheld remedy dominance.
   - "uncertain" only when the facts are too sparse or internally inconsistent to choose one of the above.

Safety: legal information, not legal advice. Hedge and explain uncertainty.
"""

_NO_RAG_JSON_SCHEMA = (
    IRAC_JSON_SCHEMA.replace(
        "- Include at least 1 supporting case citation",
        "- In no-RAG ablation modes, supporting_cases MUST be an empty list",
    ).replace(
        "- If a retrieved case is labelled PROPOSITION, copy its proposition_id into the supporting case citation",
        "- No retrieved cases are available in no-RAG ablation modes, so do not include proposition_id values",
    )
)


class IssuePredictor:
    def __init__(
        self,
        llm_client: BaseLLMClient,
        case_file: Any = None,
        *,
        prompt_pack: Any = None,
    ):
        self.llm = llm_client
        self._case_file = case_file
        self._kg_facts_by_issue: Dict[Any, Any] = {}
        # SHA-20 Phase 6: when a prompt pack is supplied, its
        # ``prediction_system`` REPLACES the default IRAC system prompt for
        # this run. The legacy IRAC text remains in use when no pack is
        # injected so existing deposit predictions stay schema-compatible.
        self._prompt_pack = prompt_pack

    @property
    def _prediction_system_prompt(self) -> str:
        if self._prompt_pack is not None and getattr(
            self._prompt_pack, "prediction_system", None
        ):
            return f"{self._prompt_pack.prediction_system}\n\n{IRAC_JSON_SCHEMA}"
        return f"{IRAC_SYSTEM_PROMPT}\n\n{IRAC_JSON_SCHEMA}"

    def _repairs_no_rag_system_prompt(self) -> str:
        return f"{_REPAIRS_NO_RAG_SYSTEM_PROMPT}\n\n{_NO_RAG_JSON_SCHEMA}"

    async def predict_no_rag(
        self,
        issues: List[IssueContext],
        prompt_mode: str = "llm_only",
    ) -> List[IssuePrediction]:
        """Predict each issue without RAG (for LLM_ONLY and KG_ONLY modes).

        prompt_mode:
          - "llm_only": uses LLM_ONLY prompt templates (no precedents, no KG fact card)
          - "kg_only": uses IRAC prompt with empty retrieved_cases but full KG fact card
        """
        results = await asyncio.gather(
            *[self._predict_issue_no_rag(issue, prompt_mode) for issue in issues],
            return_exceptions=True,
        )
        out: List[IssuePrediction] = []
        for issue, r in zip(issues, results):
            if isinstance(r, IssuePrediction):
                out.append(r)
            else:
                out.append(
                    self._uncertain_prediction(
                        issue=issue,
                        reason=f"{prompt_mode} prediction failed: {r!r}",
                        evidence_strength=self._assess_evidence_strength(issue),
                        data_impact="LLM call failed in no-RAG mode.",
                    )
                )
        return out

    async def _predict_issue_no_rag(
        self,
        issue: IssueContext,
        prompt_mode: str,
    ) -> IssuePrediction:
        """Single-issue predict for LLM_ONLY / KG_ONLY paths."""
        cf = self._case_file
        deposit_amount = "unknown"
        tenancy_duration = "unknown"
        tenancy_type = "unknown"
        region = "unknown"
        if cf is not None:
            tenancy = getattr(cf, "tenancy", None)
            prop = getattr(cf, "property", None)
            if tenancy is not None:
                if getattr(tenancy, "deposit_amount", None) is not None:
                    deposit_amount = f"{tenancy.deposit_amount:.2f}"
                if getattr(tenancy, "start_date", None) and getattr(
                    tenancy, "end_date", None
                ):
                    days = (tenancy.end_date - tenancy.start_date).days
                    months = round(days / 30.44)
                    tenancy_duration = f"{months} months ({days} days)"
                if getattr(tenancy, "tenancy_type", None):
                    tenancy_type = tenancy.tenancy_type
            if prop is not None:
                if getattr(prop, "region", None):
                    region = prop.region

        claimed_amount = issue.claimed_amount
        if claimed_amount is None:
            if issue.landlord_claim and issue.landlord_claim.claimed_amount is not None:
                claimed_amount = issue.landlord_claim.claimed_amount
            elif issue.tenant_claim and issue.tenant_claim.claimed_amount is not None:
                claimed_amount = issue.tenant_claim.claimed_amount

        tenant_claim_text = (
            issue.tenant_claim.description if issue.tenant_claim else "Not provided"
        )
        landlord_claim_text = (
            issue.landlord_claim.description if issue.landlord_claim else "Not provided"
        )

        if self._is_repairs_case(cf, issue):
            kg_fact_card = (
                self._format_kg_fact_card(self._kg_facts_by_issue.get(issue.issue_type))
                if prompt_mode == "kg_only"
                else ""
            )
            user_prompt = self._format_repairs_user_prompt(
                issue=issue,
                case_file=cf,
                claimed_amount=claimed_amount,
                tenant_claim_text=tenant_claim_text,
                landlord_claim_text=landlord_claim_text,
                evidence_summary=self._format_evidence_summary(issue),
                evidence_conflicts=self._format_evidence_conflicts(issue),
                timeline_summary=self._format_timeline(issue),
                kg_constraints="\n".join(f"- {c}" for c in issue.kg_constraints)
                if issue.kg_constraints
                else "None identified",
                kg_fact_card=kg_fact_card,
                retrieved_cases=(
                    f"No retrieved cases in {prompt_mode} mode. Leave "
                    "supporting_cases empty and do not abstain solely because "
                    "citations are unavailable."
                ),
                num_retrieved_cases=0,
            )
            system_prompt = self._repairs_no_rag_system_prompt()
        elif prompt_mode == "llm_only":
            user_prompt = LLM_ONLY_USER_PROMPT.format(
                issue_type=issue.issue_type.value,
                issue_description=issue.issue_description,
                deposit_amount=deposit_amount,
                claimed_amount=f"{claimed_amount:.2f}"
                if claimed_amount is not None
                else "unknown",
                tenancy_duration=tenancy_duration,
                tenancy_type=tenancy_type,
                region=region,
                tenant_claim=tenant_claim_text,
                landlord_claim=landlord_claim_text,
            )
            system_prompt = f"{LLM_ONLY_SYSTEM_PROMPT}\n\n{IRAC_JSON_SCHEMA}"
        else:  # kg_only — IRAC prompt with empty retrieved_cases + fact card
            kg_fact_card = self._format_kg_fact_card(
                self._kg_facts_by_issue.get(issue.issue_type)
            )
            user_prompt = IRAC_USER_PROMPT.format(
                issue_type=issue.issue_type.value,
                issue_description=issue.issue_description,
                deposit_amount=deposit_amount,
                claimed_amount=f"{claimed_amount:.2f}"
                if claimed_amount is not None
                else "unknown",
                tenancy_duration=tenancy_duration,
                tenancy_type=tenancy_type,
                region=region,
                data_completeness=issue.data_completeness,
                deposit_protection_summary="See KG fact card below."
                if kg_fact_card
                else "No deposit protection details available.",
                kg_constraints="\n".join(f"- {c}" for c in issue.kg_constraints)
                if issue.kg_constraints
                else "None identified",
                kg_fact_card=kg_fact_card,
                evidence_summary=self._format_evidence_summary(issue),
                evidence_conflicts=self._format_evidence_conflicts(issue),
                timeline_summary=self._format_timeline(issue),
                retrieved_cases="No retrieved cases in KG_ONLY mode.",
                num_retrieved_cases=0,
                tenant_claim=tenant_claim_text,
                landlord_claim=landlord_claim_text,
            )
            system_prompt = self._prediction_system_prompt

        try:
            response = await self.llm.generate(
                messages=[{"role": "user", "content": user_prompt}],
                system_prompt=system_prompt,
                max_tokens=8192,
                temperature=0.2,
            )
            prediction = self._parse_prediction_response(response, issue)
            # Force-empty citations: no retrieval ran, model must not invent.
            prediction.supporting_cases = []
            prediction.issue_type = issue.issue_type
            if not prediction.issue_description:
                prediction.issue_description = issue.issue_description
            return prediction
        except Exception as exc:
            logger.error(
                "no_rag_prediction_llm_error",
                issue_type=issue.issue_type.value,
                prompt_mode=prompt_mode,
                error=str(exc),
            )
            return self._uncertain_prediction(
                issue=issue,
                reason=f"{prompt_mode} mode LLM call failed.",
                evidence_strength=self._assess_evidence_strength(issue),
                data_impact="No-RAG path could not complete model call.",
            )

    async def predict_all(
        self,
        issues: List[IssueContext],
        retrieval_results: Dict[IssueType, IssueRetrievalResult],
        *,
        case_file: Any = None,
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
                    if case_file is None
                    else self._predict_issue(
                        issue,
                        retrieval_results[issue.issue_type],
                        case_file=case_file,
                    )
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
        *,
        case_file: Any = None,
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
        retrieved_cases_str = (
            "\n".join(formatted_cases) or "No similar cases retrieved."
        )

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

        cf = case_file if case_file is not None else self._case_file
        deposit_amount = "unknown"
        tenancy_duration = "unknown"
        tenancy_type = "unknown"
        region = "unknown"
        deposit_protection_summary = "Not specified"

        if cf is not None:
            tenancy = getattr(cf, "tenancy", None)
            prop = getattr(cf, "property", None)
            if tenancy is not None:
                if getattr(tenancy, "deposit_amount", None) is not None:
                    deposit_amount = f"{tenancy.deposit_amount:.2f}"
                if getattr(tenancy, "start_date", None) and getattr(
                    tenancy, "end_date", None
                ):
                    days = (tenancy.end_date - tenancy.start_date).days
                    months = round(days / 30.44)
                    tenancy_duration = f"{months} months ({days} days)"
                elif getattr(tenancy, "start_date", None):
                    tenancy_duration = f"Started {tenancy.start_date}, end date unknown"
                if getattr(tenancy, "tenancy_type", None):
                    tenancy_type = tenancy.tenancy_type
                deposit_protection_summary = self._build_deposit_protection_summary(
                    tenancy
                )
            if prop is not None:
                if getattr(prop, "region", None):
                    region = prop.region
                elif getattr(prop, "postcode", None):
                    region = f"postcode {prop.postcode}"

        tenant_narrative = getattr(cf, "tenant_narrative", None) if cf else None
        landlord_narrative = getattr(cf, "landlord_narrative", None) if cf else None

        tenant_claim_text = self._format_party_position(
            claim=issue.tenant_claim,
            narrative=tenant_narrative,
        )
        landlord_claim_text = self._format_party_position(
            claim=issue.landlord_claim,
            narrative=landlord_narrative,
        )

        evidence_conflicts = self._format_evidence_conflicts(issue)
        timeline_summary = self._format_timeline(issue)

        kg_fact_card = self._format_kg_fact_card(
            self._kg_facts_by_issue.get(issue.issue_type)
        )

        prompt_kwargs = {
            "issue_type": issue.issue_type.value,
            "issue_description": issue.issue_description,
            "deposit_amount": deposit_amount,
            "claimed_amount": f"{claimed_amount:.2f}"
            if claimed_amount is not None
            else "unknown",
            "tenancy_duration": tenancy_duration,
            "tenancy_type": tenancy_type,
            "region": region,
            "data_completeness": issue.data_completeness,
            "deposit_protection_summary": deposit_protection_summary,
            "kg_constraints": "\n".join(f"- {c}" for c in issue.kg_constraints)
            if issue.kg_constraints
            else "None identified",
            "kg_fact_card": kg_fact_card,
            "evidence_summary": evidence_summary,
            "evidence_conflicts": evidence_conflicts,
            "timeline_summary": timeline_summary,
            "retrieved_cases": retrieved_cases_str,
            "num_retrieved_cases": len(retrieval.results),
            "tenant_claim": tenant_claim_text,
            "landlord_claim": landlord_claim_text,
        }
        try:
            user_prompt = IRAC_USER_PROMPT.format(**prompt_kwargs)
        except KeyError:
            user_prompt = (
                f"Issue Type: {issue.issue_type.value}\n"
                f"Issue Description: {issue.issue_description}\n"
                f"Deposit Amount: £{deposit_amount}\n"
                f"Claimed Amount: £{prompt_kwargs['claimed_amount']}\n"
                f"Tenancy Duration: {tenancy_duration}\n"
                f"Data Completeness: {issue.data_completeness:.0%}\n"
                f"Deposit Protection: {deposit_protection_summary}\n\n"
                f"Tenant Claim:\n{tenant_claim_text}\n\n"
                f"Landlord Claim:\n{landlord_claim_text}\n\n"
                f"Evidence Conflicts:\n{evidence_conflicts}\n\n"
                f"KG Constraints:\n{prompt_kwargs['kg_constraints']}\n\n"
                f"Evidence Summary:\n{evidence_summary}\n\n"
                f"Timeline:\n{timeline_summary}\n\n"
                f"Retrieved Cases ({len(retrieval.results)}):\n{retrieved_cases_str}\n"
            )
        if self._is_repairs_case(cf, issue):
            user_prompt = self._format_repairs_user_prompt(
                issue=issue,
                case_file=cf,
                claimed_amount=claimed_amount,
                tenant_claim_text=tenant_claim_text,
                landlord_claim_text=landlord_claim_text,
                evidence_summary=evidence_summary,
                evidence_conflicts=evidence_conflicts,
                timeline_summary=timeline_summary,
                kg_constraints=prompt_kwargs["kg_constraints"],
                kg_fact_card=kg_fact_card,
                retrieved_cases=retrieved_cases_str,
                num_retrieved_cases=len(retrieval.results),
            )

        system_prompt = self._prediction_system_prompt

        attempts = 2
        last_response: Optional[str] = None
        for attempt in range(1, attempts + 1):
            try:
                response = await self.llm.generate(
                    messages=[{"role": "user", "content": user_prompt}],
                    system_prompt=system_prompt,
                    max_tokens=8192,
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
            data = self._extract_json_payload(response)
            if data is None:
                raise ValueError("No parseable JSON object in model response")

            if isinstance(data, list):
                data = next((item for item in data if isinstance(item, dict)), {})
            if not isinstance(data, dict):
                raise ValueError("Parsed JSON payload is not an object")

            for wrapper_key in ("issue_prediction", "prediction", "data"):
                wrapped = data.get(wrapper_key)
                if isinstance(wrapped, dict):
                    data = wrapped
                    break

            outcome_raw = data.get("outcome", data.get("predicted_outcome", "uncertain"))
            outcome = self._normalise_issue_outcome(outcome_raw)

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
                    case_ref = str(citation.get("case_reference", "Unknown"))
                    resolved_year = year if year is not None else 2024
                    citations.append(
                        Citation(
                            case_reference=case_ref,
                            year=resolved_year,
                            region=self._to_optional_str(citation.get("region")),
                            paragraph=self._to_optional_str(citation.get("paragraph")),
                            proposition_id=self._to_optional_str(
                                citation.get("proposition_id")
                            ),
                            quote=str(citation.get("quote", "")),
                            relevance=str(citation.get("relevance", "")),
                            similarity_score=self._to_probability(
                                citation.get("similarity_score", 0.0)
                            ),
                            verified=bool(citation.get("verified", False)),
                            source_url=resolve_source_url(case_ref, resolved_year),
                        )
                    )

            key_factors_raw = data.get("key_factors", [])
            key_factors = (
                [str(item) for item in key_factors_raw]
                if isinstance(key_factors_raw, list)
                else []
            )

            amount_value = self._to_optional_float(data.get("predicted_amount"))
            amount_band = self._normalise_amount_band(data.get("amount_band"))

            # 2026-05-06 — Housing Ombudsman determination ontology.
            # Optional. Missing or invalid → None (treat as legacy / non-housing prompt).
            det_raw = data.get("predicted_determination")
            predicted_determination: Optional[Determination] = None
            if det_raw:
                try:
                    predicted_determination = Determination(det_raw)
                except ValueError:
                    # LLM emitted an invalid value; treat as missing rather than crashing.
                    predicted_determination = None

            amount_construct = data.get("amount_construct")
            if amount_construct not in (
                None,
                "ordered_now",
                "previously_offered",
                "global_unapportioned",
            ):
                amount_construct = None

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
                amount_band=amount_band,
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
                predicted_determination=predicted_determination,
                amount_construct=amount_construct,
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

    def _extract_json_payload(self, response: str) -> Optional[Any]:
        cleaned = response.strip()

        if "```json" in cleaned:
            start = cleaned.find("```json") + len("```json")
            end = cleaned.find("```", start)
            cleaned = cleaned[start : end if end != -1 else None].strip()
        elif "```" in cleaned:
            start = cleaned.find("```") + len("```")
            end = cleaned.find("```", start)
            cleaned = cleaned[start : end if end != -1 else None].strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        decoder = json.JSONDecoder()
        start_positions = [idx for idx, ch in enumerate(cleaned) if ch in "[{"]

        for start in start_positions:
            try:
                parsed, _ = decoder.raw_decode(cleaned[start:])
                return parsed
            except json.JSONDecodeError:
                continue

        return None

    @staticmethod
    def _normalise_issue_outcome(value: Any) -> IssueOutcome:
        """Normalise model/forum outcome wording into shared eval labels."""
        raw = str(value or "uncertain").strip().lower()
        key = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
        exact = {
            "tenant_win": IssueOutcome.TENANT_WINS,
            "tenant_wins": IssueOutcome.TENANT_WINS,
            "resident_win": IssueOutcome.TENANT_WINS,
            "resident_wins": IssueOutcome.TENANT_WINS,
            "complaint_upheld": IssueOutcome.TENANT_WINS,
            "upheld": IssueOutcome.TENANT_WINS,
            "upheld_in_full": IssueOutcome.TENANT_WINS,
            "service_failure": IssueOutcome.TENANT_WINS,
            "maladministration": IssueOutcome.TENANT_WINS,
            "severe_maladministration": IssueOutcome.TENANT_WINS,
            "maladministration_found": IssueOutcome.TENANT_WINS,
            "finding_of_maladministration": IssueOutcome.TENANT_WINS,
            "landlord_win": IssueOutcome.LANDLORD_WINS,
            "landlord_wins": IssueOutcome.LANDLORD_WINS,
            "no_maladministration": IssueOutcome.LANDLORD_WINS,
            "no_service_failure": IssueOutcome.LANDLORD_WINS,
            "no_failure": IssueOutcome.LANDLORD_WINS,
            "complaint_not_upheld": IssueOutcome.LANDLORD_WINS,
            "not_upheld": IssueOutcome.LANDLORD_WINS,
            "split": IssueOutcome.SPLIT,
            "mixed": IssueOutcome.SPLIT,
            "mixed_findings": IssueOutcome.SPLIT,
            "partial": IssueOutcome.SPLIT,
            "partial_upheld": IssueOutcome.TENANT_WINS,
            "partially_upheld": IssueOutcome.TENANT_WINS,
            "partly_upheld": IssueOutcome.TENANT_WINS,
            "partial_maladministration": IssueOutcome.TENANT_WINS,
            "reasonable_redress": IssueOutcome.SPLIT,
            "uncertain": IssueOutcome.UNCERTAIN,
            "unknown": IssueOutcome.UNCERTAIN,
            "insufficient_evidence": IssueOutcome.UNCERTAIN,
        }
        if key in exact:
            return exact[key]
        if (
            "no_maladministration" in key
            or "no_service_failure" in key
            or "not_upheld" in key
            or "not_sustained" in key
        ):
            return IssueOutcome.LANDLORD_WINS
        if (
            "partial" in key
            or "partly" in key
            or "reasonable_redress" in key
        ):
            if "upheld" in key or "maladministration" in key:
                return IssueOutcome.TENANT_WINS
            return IssueOutcome.SPLIT
        if "mixed" in key:
            return IssueOutcome.SPLIT
        if (
            "service_failure" in key
            or "severe_maladministration" in key
            or "maladministration" in key
            or "upheld" in key
        ):
            return IssueOutcome.TENANT_WINS
        try:
            return IssueOutcome(key)
        except ValueError:
            return IssueOutcome.UNCERTAIN

    @staticmethod
    def _normalise_amount_band(value: Any) -> Optional[str]:
        if value is None:
            return None
        raw = str(value).strip().replace("£", "").replace(",", "")
        key = raw.lower().replace("gbp", "").strip()
        key = re.sub(r"\s+", "", key)
        aliases = {
            "0": "0",
            "zero": "0",
            "none": "0",
            "1-100": "1-100",
            "1to100": "1-100",
            "101-250": "101-250",
            "101to250": "101-250",
            "251-600": "251-600",
            "251to600": "251-600",
            "601-1000": "601-1000",
            "601to1000": "601-1000",
            "1000+": "1000+",
            "1001+": "1000+",
            "over1000": "1000+",
            "1000plus": "1000+",
        }
        return aliases.get(key)

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

    def _is_repairs_case(self, case_file: Any, issue: IssueContext) -> bool:
        if issue.issue_type.value in _REPAIRS_ISSUE_VALUES:
            return True
        if self._prompt_pack is not None and getattr(self._prompt_pack, "id", None) == (
            "housing.repairs_social.v1"
        ):
            return True
        metadata = getattr(case_file, "metadata", None) if case_file is not None else None
        return isinstance(metadata, dict) and (
            metadata.get("domain_id") == "housing.repairs_social.v1"
            or metadata.get("matter_type") in _REPAIRS_ISSUE_VALUES
        )

    def _format_repairs_user_prompt(
        self,
        *,
        issue: IssueContext,
        case_file: Any,
        claimed_amount: Optional[float],
        tenant_claim_text: str,
        landlord_claim_text: str,
        evidence_summary: str,
        evidence_conflicts: str,
        timeline_summary: str,
        kg_constraints: str,
        kg_fact_card: str,
        retrieved_cases: str,
        num_retrieved_cases: int,
    ) -> str:
        metadata = getattr(case_file, "metadata", None) if case_file is not None else None
        metadata = metadata if isinstance(metadata, dict) else {}
        region = "unknown"
        prop = getattr(case_file, "property", None) if case_file is not None else None
        if prop is not None and getattr(prop, "region", None):
            region = prop.region
        matter_type = metadata.get("matter_type") or issue.issue_type.value
        amount = f"£{claimed_amount:.2f}" if claimed_amount is not None else "unknown"

        kg_section = kg_fact_card or "No structured KG fact card available."
        return (
            "Forum: Housing Ombudsman Service\n"
            "Task: Predict the likely Ombudsman complaint outcome from the "
            "pre-decision resident/landlord facts and similar determinations.\n\n"
            f"Issue type: {issue.issue_type.value}\n"
            f"Matter type: {matter_type}\n"
            f"Issue description: {issue.issue_description}\n"
            f"Compensation/remedy amount in dispute: {amount}\n"
            f"Region: {region}\n"
            f"Data completeness: {issue.data_completeness:.0%}\n\n"
            f"Resident position:\n{tenant_claim_text}\n\n"
            f"Landlord position:\n{landlord_claim_text}\n\n"
            f"Evidence summary:\n{evidence_summary}\n\n"
            f"Evidence conflicts:\n{evidence_conflicts}\n\n"
            f"Timeline:\n{timeline_summary}\n\n"
            f"Structured fact card:\n{kg_section}\n\n"
            f"KG constraints:\n{kg_constraints}\n\n"
            f"Retrieved Ombudsman determinations ({num_retrieved_cases}):\n"
            f"{retrieved_cases}\n\n"
            "Before choosing the final JSON values, separate liability from "
            "remedy. In the reasoning field, include: (1) the likely "
            "Ombudsman finding for each complaint head, (2) the cited "
            "determination or user fact that supports it, (3) any cited "
            "comparator award amounts, and (4) why the final amount_band and "
            "predicted_amount follow from those comparators. If no retrieved "
            "determination contains a usable award/order amount, set "
            "predicted_amount to null and explain the amount uncertainty. "
            "Use amount_band only as a Proposer modelling band: 0, 1-100, "
            "101-250, 251-600, 601-1000, or 1000+.\n\n"
            "Return only JSON matching the required prediction schema. In the "
            "reasoning, use Housing Ombudsman outcome language: no "
            "maladministration, service failure, maladministration, severe "
            "maladministration, and remedies such as apology, repair action, "
            "compensation, case review, or policy review. In the JSON outcome "
            "field, use tenant_wins when any substantive repairs or complaint-"
            "handling issue is likely upheld or an additional resident remedy "
            "is likely, even if some complaint heads are not upheld. Use "
            "landlord_wins for likely no maladministration/no service failure. "
            "Use split only when the likely result is genuinely balanced after "
            "remedies, with material findings for both sides and no clear "
            "resident-upheld remedy dominance. Use uncertain only when the "
            "facts are too sparse or inconsistent."
        )

    @staticmethod
    def _format_party_position(
        claim: Optional[Any],
        narrative: Optional[str],
    ) -> str:
        parts: List[str] = []
        if claim is not None:
            description = getattr(claim, "description", "") or ""
            if description:
                parts.append(description)
            claimed_amount = getattr(claim, "claimed_amount", None)
            if claimed_amount is not None:
                parts.append(f"Amount claimed: £{claimed_amount:.2f}")
        if narrative:
            trimmed = narrative.strip()
            if trimmed:
                label = "Narrative" if parts else "Party narrative (no structured claim filed)"
                parts.append(f"{label}: {trimmed[:1200]}")
        return "\n".join(parts) if parts else "Not provided"

    @staticmethod
    def _get_value(obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            numeric = float(value)
            if not math.isfinite(numeric):
                return 0.0
            return numeric
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _to_optional_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(numeric):
            return None
        return numeric

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

    @staticmethod
    def _format_kg_fact_card(kg_facts: Any) -> str:
        """Render the typed KG fact card for the IRAC prompt (SHA-33).

        Returns empty string when kg_facts is None or all-unknown so the
        prompt is byte-identical to today's for cases without KG signal.
        """
        if kg_facts is None:
            return ""
        try:
            if kg_facts.is_empty():
                return ""
        except AttributeError:
            return ""

        lines = ["", "KEY KG FACTS (typed):"]
        if kg_facts.deposit_protection_status != "unknown":
            line = f"- deposit_protection_status: {kg_facts.deposit_protection_status}"
            if getattr(kg_facts, "deposit_scheme", None):
                line += f" (scheme: {kg_facts.deposit_scheme})"
            if getattr(kg_facts, "deposit_late_by_days", None) is not None:
                line += f" (late by {kg_facts.deposit_late_by_days} days)"
            lines.append(line)
        if kg_facts.prescribed_information_status != "unknown":
            line = f"- prescribed_information_status: {kg_facts.prescribed_information_status}"
            if getattr(kg_facts, "prescribed_late_by_days", None) is not None:
                line += f" (late by {kg_facts.prescribed_late_by_days} days)"
            lines.append(line)
        if kg_facts.check_in_inventory_baseline != "unknown":
            lines.append(
                f"- check_in_inventory_baseline: {kg_facts.check_in_inventory_baseline}"
            )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _build_deposit_protection_summary(tenancy: Any) -> str:
        parts: List[str] = []

        deposit_amount = getattr(tenancy, "deposit_amount", None)
        if deposit_amount is not None:
            parts.append(f"Deposit: £{deposit_amount:.2f}")

        deposit_scheme = getattr(tenancy, "deposit_scheme", None)
        deposit_protected = getattr(tenancy, "deposit_protected", None)

        if deposit_protected is True:
            scheme_text = f" in {deposit_scheme}" if deposit_scheme else ""
            parts.append(f"Protected{scheme_text}")
        elif deposit_protected is False:
            parts.append("NOT protected in any scheme")
        else:
            parts.append("Protection status unknown")

        receipt_date = getattr(tenancy, "deposit_received_date", None)
        start_date = receipt_date or getattr(tenancy, "start_date", None)
        anchor_label = "deposit receipt" if receipt_date else "tenancy start fallback"
        protection_date = getattr(tenancy, "protection_date", None)
        if protection_date and start_date:
            days = (protection_date - start_date).days
            parts.append(
                f"Protection date: {protection_date} ({days} days after {anchor_label})"
            )
            if days > 30:
                parts.append(
                    f"⚠ Late protection — exceeds 30-day statutory deadline by "
                    f"{days - 30} days (s.213 Housing Act 2004)"
                )
        elif protection_date:
            parts.append(f"Protection date: {protection_date}")

        prescribed_info = getattr(tenancy, "prescribed_info_provided", None)
        prescribed_date = getattr(tenancy, "prescribed_info_date", None)
        if prescribed_info is True:
            if prescribed_date and start_date:
                pi_days = (prescribed_date - start_date).days
                parts.append(
                    f"Prescribed information served: {prescribed_date} "
                    f"({pi_days} days after {anchor_label})"
                )
                if pi_days > 30:
                    parts.append(
                        f"⚠ Prescribed info served late — exceeds 30-day deadline by "
                        f"{pi_days - 30} days (s.213(6) Housing Act 2004)"
                    )
            else:
                parts.append("Prescribed information: provided (date unknown)")
        elif prescribed_info is False:
            parts.append(
                "⚠ Prescribed information NOT provided — "
                "separate breach under s.213(6) Housing Act 2004"
            )

        if not parts:
            return "No deposit protection details available."

        return ". ".join(parts) + "."

    @staticmethod
    def _format_evidence_conflicts(issue: "IssueContext") -> str:
        conflicts = getattr(issue, "evidence_conflicts", None)
        if not conflicts:
            return "No direct evidence conflicts identified."

        rows: List[str] = []
        for idx, conflict in enumerate(conflicts, 1):
            tenant_pos = getattr(conflict, "tenant_position", "")
            landlord_pos = getattr(conflict, "landlord_position", "")
            rows.append(
                f"Conflict {idx}:\n"
                f"  Tenant says: {tenant_pos}\n"
                f"  Landlord says: {landlord_pos}"
            )
        return "\n".join(rows)

    @staticmethod
    def _format_timeline(issue: "IssueContext") -> str:
        events = getattr(issue, "timeline_events", None)
        if not events:
            return "No timeline events recorded."

        sorted_events = sorted(
            events,
            key=lambda e: getattr(e, "date", None) or _date_type.max,
        )

        rows: List[str] = []
        for event in sorted_events:
            ev_date = getattr(event, "date", None)
            description = getattr(event, "description", "")
            source = getattr(event, "source", "")
            date_str = str(ev_date) if ev_date else "Date unknown"
            source_str = f" [{source}]" if source else ""
            rows.append(f"- {date_str}: {description}{source_str}")
        return "\n".join(rows)
