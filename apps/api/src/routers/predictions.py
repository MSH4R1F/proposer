"""
Predictions router.

Handles outcome prediction generation.
"""

from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
import structlog

from apps.api.src.dependencies import get_prediction_service
from apps.api.src.domain_runtime import (
    DomainGateStatus,
    DomainNotFoundError,
    DomainAllowlistStatus,
    resolve_domain_runtime,
)
from apps.api.src.services.prediction_service import (
    PredictionCacheConflictError,
    PredictionService,
)
from llm_orchestrator.models.prediction_v2 import PredictionResult

logger = structlog.get_logger()
router = APIRouter(prefix="/predictions", tags=["predictions"])


class PredictionRequest(BaseModel):
    """Request to generate a prediction."""

    case_id: str = Field(..., description="Case ID to generate prediction for")
    include_reasoning: bool = Field(
        default=True, description="Include full reasoning trace"
    )
    # SHA-20 Phase 3: optional domain selector. Omitted requests behave
    # exactly as today (default housing.deposit.v1, deposit semantics).
    domain_id: Optional[str] = Field(
        default=None,
        description=(
            "Optional domain id (e.g. 'housing.deposit.v1'). Omit for default "
            "deposit behaviour. Disabled / unknown domains return a 4xx with "
            "code 'domain_unavailable' or 'domain_not_found'."
        ),
    )


class IssuePredictionResponse(BaseModel):
    """Prediction for a single issue."""

    issue_type: str
    issue_description: str = ""
    predicted_outcome: str
    confidence: float
    raw_confidence: Optional[float] = None
    predicted_amount: Optional[float] = None
    amount_range: Optional[List[float]] = None
    reasoning: str
    key_factors: List[str] = []
    supporting_cases: List[Dict[str, Any]] = []
    evidence_strength: Optional[str] = None
    counterfactuals: Optional[List[Dict[str, Any]]] = None


class PredictionResponse(BaseModel):
    """Response with prediction results."""

    case_id: str
    prediction_id: str
    overall_outcome: str
    overall_confidence: float
    outcome_summary: str

    tenant_recovery_amount: Optional[float] = None
    landlord_recovery_amount: Optional[float] = None
    predicted_settlement_range: Optional[List[float]] = None

    issue_predictions: List[IssuePredictionResponse] = []

    key_strengths: List[str] = []
    key_weaknesses: List[str] = []
    uncertainties: List[str] = []

    retrieved_cases: List[str] = []
    total_cases_analyzed: int = 0

    reasoning_trace: Optional[List[Dict[str, Any]]] = None

    pipeline_version: str = "v2"
    citation_verification: Optional[Dict[str, Any]] = None
    pipeline_metadata: Optional[Dict[str, Any]] = None

    disclaimer: str


def _prediction_to_response(
    prediction: Union[PredictionResult, Dict[str, Any]],
    *,
    include_reasoning: bool = True,
) -> PredictionResponse:
    """Serialize persisted and freshly generated predictions with one DTO shape."""
    if isinstance(prediction, dict):
        prediction = PredictionResult.model_validate(prediction)

    issue_preds = [
        IssuePredictionResponse(
            issue_type=ip.issue_type.value,
            issue_description=ip.issue_description or "",
            predicted_outcome=ip.outcome.value,
            confidence=(
                ip.calibrated_confidence
                if ip.calibrated_confidence is not None
                else (ip.raw_confidence if ip.raw_confidence is not None else 0.0)
            ),
            raw_confidence=ip.raw_confidence,
            predicted_amount=ip.predicted_amount,
            amount_range=list(ip.amount_range) if ip.amount_range else None,
            reasoning=ip.reasoning or "",
            key_factors=ip.key_factors or [],
            supporting_cases=[
                c.model_dump(mode="json") for c in (ip.supporting_cases or [])
            ],
            evidence_strength=ip.evidence_strength.value
            if ip.evidence_strength
            else None,
            counterfactuals=[c.model_dump(mode="json") for c in ip.counterfactuals]
            if ip.counterfactuals
            else None,
        )
        for ip in prediction.issue_predictions
    ]

    reasoning_trace = None
    if include_reasoning:
        reasoning_trace = [
            {
                "step_number": step.step_number,
                "category": step.category,
                "title": step.title,
                "content": step.content,
                "citations": [c.model_dump(mode="json") for c in step.citations],
                "confidence": step.confidence,
            }
            for step in prediction.reasoning_trace
        ]

    return PredictionResponse(
        case_id=prediction.case_id,
        prediction_id=prediction.prediction_id,
        overall_outcome=prediction.overall_outcome.value,
        overall_confidence=prediction.overall_confidence,
        outcome_summary=prediction.outcome_summary,
        tenant_recovery_amount=prediction.tenant_recovery_amount,
        landlord_recovery_amount=prediction.landlord_recovery_amount,
        predicted_settlement_range=(
            list(prediction.predicted_settlement_range)
            if prediction.predicted_settlement_range
            else None
        ),
        issue_predictions=issue_preds,
        key_strengths=prediction.key_strengths,
        key_weaknesses=prediction.key_weaknesses,
        uncertainties=prediction.uncertainties,
        retrieved_cases=prediction.retrieved_cases,
        total_cases_analyzed=prediction.total_cases_analyzed,
        reasoning_trace=reasoning_trace,
        pipeline_version=getattr(prediction, "pipeline_version", "v2"),
        citation_verification=(
            prediction.citation_verification.model_dump(mode="json")
            if prediction.citation_verification
            else None
        ),
        pipeline_metadata=(
            prediction.pipeline_metadata.model_dump(mode="json")
            if prediction.pipeline_metadata
            else None
        ),
        disclaimer=prediction.disclaimer,
    )


@router.post("/generate", response_model=PredictionResponse)
async def generate_prediction(
    request: PredictionRequest,
    prediction_service: PredictionService = Depends(get_prediction_service),
):
    """
    Generate an outcome prediction for a case.

    Requires a complete case file (from intake).
    Returns prediction with reasoning trace and citations.
    """
    logger.debug(
        "generate_prediction_request",
        case_id=request.case_id,
        include_reasoning=request.include_reasoning,
        domain_id=request.domain_id,
    )

    # SHA-20 Phase 3: resolve domain runtime context. Only build one when the
    # caller passed a domain_id explicitly OR when we want to record domain
    # metadata for the default deposit run. We always resolve so that the
    # prediction is stamped with the correct (default deposit) domain block.
    try:
        domain_runtime = resolve_domain_runtime(
            request.domain_id,
            user_id=None,  # Auth not yet wired; Phase 8 plugs in Supabase UUIDs.
        )
    except DomainNotFoundError as exc:
        logger.warning(
            "prediction_request_unknown_domain",
            requested_domain=request.domain_id,
            error=str(exc),
        )
        raise HTTPException(
            status_code=400,
            detail={
                "code": "domain_not_found",
                "message": f"Unknown domain id: {request.domain_id}",
            },
        )

    if not domain_runtime.is_usable:
        logger.warning(
            "prediction_request_domain_unavailable",
            requested_domain=request.domain_id,
            resolved_domain=domain_runtime.domain_id,
            gate_status=domain_runtime.gate_status.value,
            allowlist_status=domain_runtime.allowlist_status.value,
        )
        raise HTTPException(
            status_code=403,
            detail={
                "code": "domain_unavailable",
                "message": (
                    f"Domain {domain_runtime.domain_id!r} is not available "
                    f"(gate={domain_runtime.gate_status.value}, "
                    f"allowlist={domain_runtime.allowlist_status.value})."
                ),
                "domain_id": domain_runtime.domain_id,
                "gate_status": domain_runtime.gate_status.value,
                "allowlist_status": domain_runtime.allowlist_status.value,
            },
        )

    try:
        # Check if case exists and is complete
        logger.debug("checking_case_ready", case_id=request.case_id)
        case_status = await prediction_service.check_case_ready(request.case_id)

        logger.debug(
            "case_status_checked",
            case_id=request.case_id,
            exists=case_status["exists"],
            is_complete=case_status["is_complete"],
            completeness=case_status.get("completeness", 0),
        )

        if not case_status["exists"]:
            logger.warning("case_not_found_for_prediction", case_id=request.case_id)
            raise HTTPException(
                status_code=404, detail=f"Case not found: {request.case_id}"
            )

        completeness = case_status.get("completeness", 0)
        if completeness < 0.5:
            logger.warning(
                "case_insufficient_for_prediction",
                case_id=request.case_id,
                completeness=completeness,
                missing_info=case_status["missing_info"],
            )
            raise HTTPException(
                status_code=400,
                detail=f"Not enough information to generate a prediction. "
                f"Completeness: {completeness:.0%}. "
                f"Please provide at least 50% of case details before generating a prediction.",
            )

        if not case_status["is_complete"]:
            logger.info(
                "generating_prediction_with_incomplete_case",
                case_id=request.case_id,
                completeness=completeness,
                missing_info=case_status["missing_info"],
            )

        # Generate prediction
        logger.debug("calling_prediction_service", case_id=request.case_id)
        prediction = await prediction_service.generate_prediction(
            case_id=request.case_id,
            include_reasoning=request.include_reasoning,
            domain_runtime=domain_runtime,
        )

        logger.info(
            "prediction_generated",
            case_id=request.case_id,
            prediction_id=prediction.prediction_id,
            overall_outcome=prediction.overall_outcome.value,
            confidence=prediction.overall_confidence,
            num_issues=len(prediction.issue_predictions),
            num_cases_analyzed=prediction.total_cases_analyzed,
        )

        return _prediction_to_response(
            prediction,
            include_reasoning=request.include_reasoning,
        )

    except HTTPException:
        raise
    except PredictionCacheConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(
            "generate_prediction_failed",
            case_id=request.case_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/case/{case_id}")
async def get_predictions_for_case(
    case_id: str,
    prediction_service: PredictionService = Depends(get_prediction_service),
):
    """
    List all predictions for a case.
    """
    logger.debug("list_predictions_for_case_request", case_id=case_id)
    try:
        predictions = await prediction_service.list_predictions_for_case(case_id)

        logger.debug(
            "list_predictions_success",
            case_id=case_id,
            prediction_count=len(predictions),
        )

        return {"case_id": case_id, "predictions": predictions}
    except Exception as e:
        logger.error(
            "list_predictions_failed",
            case_id=case_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/check/{case_id}")
async def check_case_ready(
    case_id: str,
    prediction_service: PredictionService = Depends(get_prediction_service),
):
    """
    Check if a case is ready for prediction and return data quality info.

    Returns quality tier, missing required/recommended fields, and completeness.
    """
    logger.debug("check_case_ready_request", case_id=case_id)
    try:
        result = await prediction_service.check_case_ready(case_id)

        if not result["exists"]:
            raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("check_case_ready_failed", case_id=case_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{prediction_id}", response_model=PredictionResponse)
async def get_prediction(
    prediction_id: str,
    prediction_service: PredictionService = Depends(get_prediction_service),
):
    """
    Retrieve a previously generated prediction.
    """
    logger.debug("get_prediction_request", prediction_id=prediction_id)
    try:
        prediction = await prediction_service.get_prediction(prediction_id)

        if not prediction:
            logger.warning("prediction_not_found", prediction_id=prediction_id)
            raise HTTPException(
                status_code=404, detail=f"Prediction not found: {prediction_id}"
            )

        logger.debug("prediction_retrieved", prediction_id=prediction_id)
        return _prediction_to_response(prediction, include_reasoning=True)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_prediction_failed",
            prediction_id=prediction_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(status_code=500, detail=str(e))
