import structlog
from typing import Any, Dict, List, Optional

from ..models.case_file import CaseFile
from ..models.prediction_v2 import (
    Citation,
    Determination,
    EvidenceStrength,
    IssueContext,
    IssueOutcome,
    IssuePrediction,
    IssueRetrievalResult,
    IssueType,
    OutcomeType,
    PipelineMetadata,
    PredictionResult,
    ReasoningStep,
    VerificationResult,
)
from .evidence_path_validator import EvidencePathValidator

logger = structlog.get_logger()


# SHA-20 Phase 6 (audit D3): the deposit_protection IssueType is overloaded
# across two materially different matters. Route penalty-branch logic ONLY
# when the matter_type is explicitly the non-protection penalty matter.
_DEPOSIT_DEDUCTION_MATTER = "deposit_deduction"
_DEPOSIT_NON_PROTECTION_MATTER = "deposit_non_protection"


def _aggregate_determination(
    issue_predictions: List[IssuePrediction],
) -> Optional[Determination]:
    """Take the modal Determination across non-uncertain issues.

    Tie-breaker: most severe class wins, by the order
    severe_maladministration > maladministration > service_failure >
    reasonable_redress > no_maladministration > resolved_with_intervention >
    outside_jurisdiction. Returns None if no issue carries a determination.
    """
    from collections import Counter

    severity = {
        Determination.SEVERE_MALADMINISTRATION: 6,
        Determination.MALADMINISTRATION: 5,
        Determination.SERVICE_FAILURE: 4,
        Determination.REASONABLE_REDRESS: 3,
        Determination.NO_MALADMINISTRATION: 2,
        Determination.RESOLVED_WITH_INTERVENTION: 1,
        Determination.OUTSIDE_JURISDICTION: 0,
    }
    determinations = [
        ip.predicted_determination
        for ip in issue_predictions
        if getattr(ip, "predicted_determination", None) is not None
    ]
    if not determinations:
        return None
    counts = Counter(determinations)
    max_count = max(counts.values())
    candidates = [d for d, c in counts.items() if c == max_count]
    return max(candidates, key=lambda d: severity.get(d, -1))


class OutputAssembler:
    def assemble(
        self,
        case_file: CaseFile,
        issues: List[IssueContext],
        issue_predictions: List[IssuePrediction],
        retrieval_results: Dict[IssueType, IssueRetrievalResult],
        verification: VerificationResult,
        pipeline_metadata: PipelineMetadata,
        *,
        matter_type: Optional[str] = None,
        case_graph: Optional[Any] = None,
    ) -> PredictionResult:
        # SHA-20 Phase 6 (audit D3): resolve the matter_type so the
        # deposit_protection penalty branch (1x-3x) only fires for the
        # non-protection matter. For backwards compat with pre-Phase-6
        # predictions whose CaseFile carries no matter information, default
        # to deposit_deduction and emit a structured warning.
        resolved_matter_type = self._resolve_matter_type(case_file, matter_type)
        issue_map: Dict[IssueType, IssueContext] = {
            issue.issue_type: issue for issue in issues
        }
        deposit_raw = case_file.tenancy.deposit_amount
        deposit = self._to_float(deposit_raw)
        deposit_cap = deposit_raw if deposit_raw is not None else float("inf")

        tenant_recovery = 0.0
        landlord_recovery = 0.0
        penalty_recovery = 0.0
        uncertain_count = 0
        non_uncertain_for_conf: List[IssuePrediction] = []
        has_explicit_recovery_amount = False

        for prediction in issue_predictions:
            amount_is_explicit = prediction.predicted_amount is not None
            amount = (
                self._to_float(prediction.predicted_amount)
                if amount_is_explicit
                else 0.0
            )
            if prediction.outcome == IssueOutcome.UNCERTAIN:
                uncertain_count += 1
                continue

            non_uncertain_for_conf.append(prediction)
            if amount_is_explicit:
                has_explicit_recovery_amount = True
            # Audit D3 split: penalty branch only when matter_type explicitly
            # signals the non-protection penalty matter. Otherwise (the
            # default deposit_deduction matter) treat deposit_protection
            # outcomes as standard issue-by-issue recovery.
            is_penalty_issue = (
                prediction.issue_type == IssueType.DEPOSIT_PROTECTION
                and resolved_matter_type == _DEPOSIT_NON_PROTECTION_MATTER
            )

            if prediction.outcome == IssueOutcome.TENANT_WINS:
                if is_penalty_issue:
                    penalty_recovery += max(0.0, amount)
                else:
                    tenant_recovery += max(0.0, amount)
            elif prediction.outcome == IssueOutcome.LANDLORD_WINS:
                landlord_recovery += max(0.0, amount)
            elif prediction.outcome == IssueOutcome.SPLIT:
                if amount > 0:
                    tenant_recovery += amount
                else:
                    half = abs(amount) / 2.0
                    tenant_recovery += half
                    landlord_recovery += half

        tenant_recovery = min(max(0.0, tenant_recovery), deposit_cap)
        landlord_recovery = min(max(0.0, landlord_recovery), deposit_cap)
        tenant_recovery += penalty_recovery

        overall_outcome = self._determine_overall_outcome(
            deposit=deposit,
            issue_predictions=issue_predictions,
            tenant_recovery=tenant_recovery,
            landlord_recovery=landlord_recovery,
            uncertain_count=uncertain_count,
        )

        overall_confidence = self._aggregate_confidence(
            non_uncertain_for_conf, issue_map
        )

        reasoning_trace = self._build_reasoning_trace(
            issues=issues,
            issue_predictions=issue_predictions,
            verification=verification,
        )

        settlement_range = (
            self._build_settlement_range(tenant_recovery, deposit)
            if has_explicit_recovery_amount
            else None
        )

        retrieved_cases = sorted(
            {
                c.case_reference
                for c in verification.verified_citations
                if c.case_reference and c.verified
            }
        )
        if not retrieved_cases:
            retrieved_cases = sorted(
                {
                    c.case_reference
                    for c in verification.verified_citations
                    if c.case_reference
                }
            )

        analyzed_case_refs = set()
        merged_temporal_distribution: Dict[int, int] = {}
        rag_conf_values: List[float] = []
        sufficient_flags: List[bool] = []

        for retrieval in retrieval_results.values():
            sufficient_flags.append(bool(retrieval.is_sufficient))
            rag_conf_values.append(self._bounded_probability(retrieval.rag_confidence))

            for result in retrieval.results:
                case_ref = self._get_value(result, "case_reference")
                if case_ref:
                    analyzed_case_refs.add(str(case_ref))

            for year, count in retrieval.temporal_distribution.items():
                year_int = self._to_int(year)
                if year_int is None:
                    continue
                count_int = self._to_int(count, 0) or 0
                merged_temporal_distribution[year_int] = (
                    merged_temporal_distribution.get(year_int, 0) + count_int
                )

        key_strengths: List[str] = []
        key_weaknesses: List[str] = []
        uncertainties: List[str] = []
        missing_information: List[str] = []

        for issue in issues:
            if issue.data_completeness < 0.5:
                missing_information.append(
                    f"Incomplete issue data for {issue.issue_type.value} (completeness={issue.data_completeness:.2f})."
                )

        for prediction in issue_predictions:
            if prediction.evidence_strength == EvidenceStrength.STRONG:
                if prediction.key_factors:
                    key_strengths.extend(prediction.key_factors)
                else:
                    key_strengths.append(
                        f"Strong evidence on {prediction.issue_type.value}: {prediction.issue_description or prediction.reasoning[:120]}"
                    )

            if prediction.evidence_strength in {
                EvidenceStrength.WEAK,
                EvidenceStrength.INSUFFICIENT,
            }:
                key_weaknesses.append(
                    f"{prediction.issue_type.value}: evidence is {prediction.evidence_strength.value}."
                )
                if prediction.evidence_strength == EvidenceStrength.INSUFFICIENT:
                    uncertainties.append(
                        f"Missing precedent/evidence for issue {prediction.issue_type.value}."
                    )

            if prediction.outcome == IssueOutcome.UNCERTAIN:
                uncertainties.append(
                    f"Uncertain outcome for {prediction.issue_type.value}: {prediction.reasoning or 'insufficient certainty.'}"
                )

        key_strengths = self._dedupe_preserve_order(key_strengths)
        key_weaknesses = self._dedupe_preserve_order(key_weaknesses)
        uncertainties = self._dedupe_preserve_order(uncertainties)
        missing_information = self._dedupe_preserve_order(missing_information)

        rag_confidence = (
            sum(rag_conf_values) / len(rag_conf_values) if rag_conf_values else 0.0
        )
        retrieval_quality = self._compute_retrieval_quality(sufficient_flags)

        outcome_summary = self._build_outcome_summary(
            overall_outcome=overall_outcome,
            tenant_recovery=tenant_recovery,
            landlord_recovery=landlord_recovery,
            uncertain_count=uncertain_count,
            total_issues=len(issue_predictions),
            amounts_known=has_explicit_recovery_amount,
        )

        # Stream C PR 6 Tasks 6.1 + 6.2 / Cross-PR Contracts C4 + C5:
        # walk EvidenceSpan → FactorAssertion → Proposition → OutcomeComponent
        # for each claimed outcome component. In strict mode
        # (STREAM_C_EVIDENCE_PATH_STRICT=1), rejected components force the
        # owning IssuePrediction's outcome to UNCERTAIN. In audit mode
        # (default), results are recorded only.
        evidence_path_results: List[Dict[str, Any]] = []
        if case_graph is not None:
            validator = EvidencePathValidator(case_graph=case_graph)
            for issue_pred in issue_predictions:
                outcome_components = getattr(issue_pred, "outcome_components", []) or []
                for oc in outcome_components:
                    result = validator.validate_outcome_component(oc)
                    evidence_path_results.append(result.model_dump())
                    if result.abstention_required:
                        try:
                            issue_pred.outcome = IssueOutcome.UNCERTAIN
                        except Exception:  # pragma: no cover — frozen-model guard
                            pass
        pipeline_metadata.evidence_path_results = evidence_path_results

        prediction = PredictionResult(
            case_id=case_file.case_id,
            overall_outcome=overall_outcome,
            overall_confidence=overall_confidence,
            outcome_summary=outcome_summary,
            tenant_recovery_amount=(
                tenant_recovery if has_explicit_recovery_amount else None
            ),
            landlord_recovery_amount=(
                landlord_recovery if has_explicit_recovery_amount else None
            ),
            predicted_settlement_range=settlement_range,
            deposit_at_stake=case_file.tenancy.deposit_amount,
            issue_predictions=issue_predictions,
            predicted_determination=_aggregate_determination(issue_predictions),
            reasoning_trace=reasoning_trace,
            key_strengths=key_strengths,
            key_weaknesses=key_weaknesses,
            uncertainties=uncertainties,
            missing_information=missing_information,
            retrieved_cases=retrieved_cases,
            total_cases_analyzed=len(analyzed_case_refs),
            retrieval_evidence=self._build_retrieval_evidence(retrieval_results),
            rag_confidence=self._bounded_probability(rag_confidence),
            retrieval_quality=retrieval_quality,
            citation_verification=verification,
            temporal_distribution=merged_temporal_distribution or None,
            pipeline_metadata=pipeline_metadata,
        )

        # Stamp the resolved matter_type onto metadata so downstream callers
        # (and the regression assertions in test_output_assembler_matter_split)
        # can verify which branch was taken.
        prediction.metadata["matter_type"] = resolved_matter_type
        prediction.metadata["penalty_recovery"] = penalty_recovery

        self._validate_prediction(prediction, verification)
        logger.info(
            "output_assembled",
            case_id=case_file.case_id,
            overall_outcome=prediction.overall_outcome.value,
            confidence=prediction.overall_confidence,
            issues=len(issue_predictions),
            verified_citations=len(verification.verified_citations),
            matter_type=resolved_matter_type,
            penalty_recovery=penalty_recovery,
        )
        return prediction

    def _determine_overall_outcome(
        self,
        deposit: float,
        issue_predictions: List[IssuePrediction],
        tenant_recovery: float,
        landlord_recovery: float,
        uncertain_count: int,
    ) -> OutcomeType:
        if deposit > 0:
            if tenant_recovery > 0.7 * deposit:
                return OutcomeType.TENANT_WIN
            if landlord_recovery > 0.7 * deposit:
                return OutcomeType.LANDLORD_WIN
            if issue_predictions and uncertain_count > (len(issue_predictions) / 2):
                return OutcomeType.UNCERTAIN
            return OutcomeType.SPLIT

        counts: Dict[IssueOutcome, int] = {}
        for prediction in issue_predictions:
            counts[prediction.outcome] = counts.get(prediction.outcome, 0) + 1

        if not counts:
            return OutcomeType.UNCERTAIN

        max_count = max(counts.values())
        top = [outcome for outcome, count in counts.items() if count == max_count]
        if len(top) != 1:
            return OutcomeType.SPLIT

        outcome = top[0]
        if outcome == IssueOutcome.TENANT_WINS:
            return OutcomeType.TENANT_WIN
        if outcome == IssueOutcome.LANDLORD_WINS:
            return OutcomeType.LANDLORD_WIN
        if outcome == IssueOutcome.UNCERTAIN:
            return OutcomeType.UNCERTAIN
        return OutcomeType.SPLIT

    def _aggregate_confidence(
        self,
        non_uncertain: List[IssuePrediction],
        issue_map: Dict[IssueType, IssueContext],
    ) -> float:
        if not non_uncertain:
            return 0.0

        weighted_conf = 0.0
        total_weight = 0.0
        for prediction in non_uncertain:
            issue = issue_map.get(prediction.issue_type)
            weight = self._to_float(issue.claimed_amount if issue else None)
            if weight <= 0:
                weight = 1.0
            weighted_conf += (
                self._bounded_probability(prediction.raw_confidence) * weight
            )
            total_weight += weight

        if total_weight <= 0:
            return 0.0
        return self._bounded_probability(weighted_conf / total_weight)

    def _build_reasoning_trace(
        self,
        issues: List[IssueContext],
        issue_predictions: List[IssuePrediction],
        verification: VerificationResult,
    ) -> List[ReasoningStep]:
        issue_lines = []
        for issue in issues:
            issue_lines.append(
                f"- {issue.issue_type.value}: completeness={issue.data_completeness:.2f}"
            )

        reasoning_steps = [
            ReasoningStep(
                step_number=1,
                category="decomposition",
                title="Issue Decomposition",
                content=(
                    "Issues identified and assessed for data completeness:\n"
                    + (
                        "\n".join(issue_lines)
                        if issue_lines
                        else "- No issues identified"
                    )
                ),
                citations=[],
                confidence=0.95,
            )
        ]

        for prediction in issue_predictions:
            reasoning_steps.append(
                ReasoningStep(
                    step_number=len(reasoning_steps) + 1,
                    category="issue_analysis",
                    title=f"Issue Analysis: {prediction.issue_type.value}",
                    content=prediction.reasoning,
                    citations=prediction.supporting_cases,
                    confidence=self._bounded_probability(prediction.raw_confidence),
                )
            )

        verification_summary = (
            f"Verified citations: {len(verification.verified_citations)}. "
            f"Removed citations: {len(verification.removed_citations)}. "
            f"Removal rate: {verification.removal_rate:.2f}. "
            f"All citations valid: {verification.all_citations_valid}. "
            f"Needs re-prediction: {verification.needs_reprediction}."
        )
        reasoning_steps.append(
            ReasoningStep(
                step_number=len(reasoning_steps) + 1,
                category="verification",
                title="Citation Verification",
                content=verification_summary,
                citations=verification.verified_citations,
                confidence=1.0 if verification.all_citations_valid else 0.6,
            )
        )

        return reasoning_steps

    def _build_settlement_range(
        self, central_estimate: float, deposit: float
    ) -> tuple[float, float]:
        central = max(0.0, self._to_float(central_estimate))
        low = max(0.0, central * 0.85)
        high = central * 1.15
        max_possible = deposit * 3.0 if deposit > 0 else float("inf")
        if max_possible < float("inf"):
            high = min(max_possible, high)
        if low > high:
            low = high
        return (low, high)

    def _compute_retrieval_quality(self, sufficient_flags: List[bool]) -> str:
        if not sufficient_flags:
            return "poor"
        sufficient = sum(1 for flag in sufficient_flags if flag)
        total = len(sufficient_flags)
        insufficient = total - sufficient
        if insufficient == 0:
            return "good"
        if insufficient > total / 2:
            return "poor"
        return "limited"

    def _build_outcome_summary(
        self,
        overall_outcome: OutcomeType,
        tenant_recovery: float,
        landlord_recovery: float,
        uncertain_count: int,
        total_issues: int,
        amounts_known: bool = True,
    ) -> str:
        base = f"Predicted overall outcome: {overall_outcome.value.replace('_', ' ')}. "
        if amounts_known:
            base += (
                f"Estimated tenant recovery: £{tenant_recovery:.2f}. "
                f"Estimated landlord recovery: £{landlord_recovery:.2f}."
            )
        else:
            base += (
                "Monetary remedy amount unknown because no issue-level "
                "prediction emitted an explicit amount."
            )
        if uncertain_count > 0:
            base += f" {uncertain_count}/{total_issues} issues remain uncertain."
        return base

    def _build_retrieval_evidence(
        self,
        retrieval_results: Dict[IssueType, IssueRetrievalResult],
    ) -> Dict[str, Any]:
        """Return compact retrieval diagnostics for eval artifacts."""
        evidence: Dict[str, Any] = {}
        for issue_type, retrieval in retrieval_results.items():
            issue_key = getattr(issue_type, "value", str(issue_type))
            evidence[issue_key] = {
                "query_used": retrieval.query_used,
                "is_sufficient": bool(retrieval.is_sufficient),
                "rag_confidence": self._bounded_probability(
                    retrieval.rag_confidence
                ),
                "legislative_regime": retrieval.legislative_regime,
                "temporal_distribution": dict(retrieval.temporal_distribution),
                "results": [
                    self._serialise_retrieval_result(result, rank=index)
                    for index, result in enumerate(retrieval.results, start=1)
                ],
            }
        return evidence

    def _serialise_retrieval_result(self, result: Any, *, rank: int) -> Dict[str, Any]:
        text = self._get_value(
            result,
            "chunk_text",
            self._get_value(result, "text", ""),
        )
        source_metadata = self._get_value(result, "source_metadata", None)
        source_id = self._get_value(result, "source_id", None)
        source_kind = self._get_value(result, "source_kind", None)
        if source_metadata is not None:
            source_id = source_id or self._get_value(source_metadata, "source_id", None)
            source_kind = source_kind or self._get_value(
                source_metadata, "source_kind", None
            )

        return {
            "rank": rank,
            "chunk_id": self._json_scalar(self._get_value(result, "chunk_id", None)),
            "source_id": self._json_scalar(source_id),
            "source_kind": self._json_scalar(source_kind),
            "case_reference": self._json_scalar(
                self._get_value(result, "case_reference", None)
            ),
            "year": self._json_scalar(self._get_value(result, "year", None)),
            "paragraph": self._json_scalar(self._get_value(result, "paragraph", None)),
            "section_type": self._json_scalar(
                self._get_value(result, "section_type", None)
            ),
            "combined_score": self._optional_float(
                self._get_value(result, "combined_score", None)
            ),
            "semantic_score": self._optional_float(
                self._get_value(result, "semantic_score", None)
            ),
            "bm25_score": self._optional_float(
                self._get_value(result, "bm25_score", None)
            ),
            "rerank_score": self._optional_float(
                self._get_value(result, "rerank_score", None)
            ),
            "repairs_issue_match_score": self._optional_float(
                self._get_value(result, "repairs_issue_match_score", None)
            ),
            "ombudsman_outcome_signal_score": self._optional_float(
                self._get_value(result, "ombudsman_outcome_signal_score", None)
            ),
            "text_preview": str(text)[:500] if text else "",
        }

    def _validate_prediction(
        self,
        prediction: PredictionResult,
        verification: VerificationResult,
    ) -> None:
        if prediction.predicted_settlement_range:
            low, high = prediction.predicted_settlement_range
            if low > high:
                prediction.predicted_settlement_range = (high, high)

        if prediction.tenant_recovery_amount is not None:
            prediction.tenant_recovery_amount = max(
                0.0, self._to_float(prediction.tenant_recovery_amount)
            )
        if prediction.landlord_recovery_amount is not None:
            prediction.landlord_recovery_amount = max(
                0.0, self._to_float(prediction.landlord_recovery_amount)
            )

        has_citations = bool(verification.verified_citations)
        has_non_uncertain_predictions = any(
            ip.outcome != IssueOutcome.UNCERTAIN for ip in prediction.issue_predictions
        )
        if not has_citations:
            if not has_non_uncertain_predictions:
                prediction.overall_outcome = OutcomeType.UNCERTAIN
                prediction.uncertainties = self._dedupe_preserve_order(
                    prediction.uncertainties
                    + [
                        "No verified citations and no confident predictions; "
                        "result marked uncertain under cite-or-abstain."
                    ]
                )
            else:
                prediction.overall_confidence = min(prediction.overall_confidence, 0.4)
                prediction.uncertainties = self._dedupe_preserve_order(
                    prediction.uncertainties
                    + [
                        "No verified citations — confidence reduced. "
                        "Predictions are based on model reasoning without "
                        "verified case law references."
                    ]
                )

    @staticmethod
    def _resolve_matter_type(
        case_file: CaseFile,
        explicit: Optional[str],
    ) -> str:
        """Pick the effective matter_type for the deposit-domain branch split.

        Priority:
            1. ``explicit`` argument (from the prediction engine / runtime).
            2. ``case_file.metadata['matter_type']`` if set.
            3. First entry of ``case_file.matter_types`` if non-empty.
            4. Default ``deposit_deduction`` (audit D3 backwards-compat
               default — a pre-Phase-6 persisted CaseFile has none of the
               above, and the established behaviour for those predictions
               is the deposit-deduction branch).
        """
        if explicit:
            return explicit
        meta = getattr(case_file, "metadata", None)
        if isinstance(meta, dict):
            value = meta.get("matter_type")
            if isinstance(value, str) and value:
                return value
        matter_types = getattr(case_file, "matter_types", None)
        if matter_types:
            return matter_types[0]
        logger.warning(
            "matter_type_missing_defaulting_to_deposit_deduction",
            case_id=getattr(case_file, "case_id", "unknown"),
        )
        return _DEPOSIT_DEDUCTION_MATTER

    @staticmethod
    def _get_value(obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    @staticmethod
    def _to_float(value: Optional[Any]) -> float:
        if value is None:
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _optional_float(value: Optional[Any]) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _json_scalar(value: Any) -> Any:
        return getattr(value, "value", value)

    @staticmethod
    def _to_int(value: Any, default: Optional[int] = None) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _bounded_probability(value: Any) -> float:
        numeric = OutputAssembler._to_float(value)
        return max(0.0, min(1.0, numeric))

    @staticmethod
    def _dedupe_preserve_order(items: List[str]) -> List[str]:
        seen = set()
        deduped = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return deduped
