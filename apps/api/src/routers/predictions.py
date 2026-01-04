"""
Predictions router.

Handles outcome prediction generation.
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from ..services.prediction_service import PredictionService, get_prediction_service

router = APIRouter(prefix="/predictions", tags=["predictions"])


class PredictionRequest(BaseModel):
    """Request to generate a prediction."""
    case_id: str = Field(..., description="Case ID to generate prediction for")
    include_reasoning: bool = Field(default=True, description="Include full reasoning trace")


class IssuePredictionResponse(BaseModel):
    """Prediction for a single issue."""
    issue_type: str
    predicted_outcome: str
    confidence: float
    reasoning: str
    key_factors: List[str] = []


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

    reasoning_trace: Optional[List[Dict]] = None

    disclaimer: str


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
    try:
        # Check if case exists and is complete
        case_status = await prediction_service.check_case_ready(request.case_id)

        if not case_status["exists"]:
            raise HTTPException(status_code=404, detail=f"Case not found: {request.case_id}")

        if not case_status["is_complete"]:
            raise HTTPException(
                status_code=400,
                detail=f"Intake not complete. Completeness: {case_status['completeness']:.0%}. "
                       f"Missing: {', '.join(case_status['missing_info'])}"
            )

        # Generate prediction
        prediction = await prediction_service.generate_prediction(
            case_id=request.case_id,
            include_reasoning=request.include_reasoning,
        )

        # Convert to response
        issue_preds = [
            IssuePredictionResponse(
                issue_type=ip.issue_type,
                predicted_outcome=ip.predicted_outcome.value,
                confidence=ip.confidence,
                reasoning=ip.reasoning,
                key_factors=ip.key_factors,
            )
            for ip in prediction.issue_predictions
        ]

        reasoning_trace = None
        if request.include_reasoning:
            reasoning_trace = [
                {
                    "step_number": step.step_number,
                    "category": step.category,
                    "title": step.title,
                    "content": step.content,
                    "citations": [c.model_dump() for c in step.citations],
                }
                for step in prediction.reasoning_trace
            ]

        settlement_range = None
        if prediction.predicted_settlement_range:
            settlement_range = list(prediction.predicted_settlement_range)

        return PredictionResponse(
            case_id=prediction.case_id,
            prediction_id=prediction.prediction_id,
            overall_outcome=prediction.overall_outcome.value,
            overall_confidence=prediction.overall_confidence,
            outcome_summary=prediction.outcome_summary,
            tenant_recovery_amount=prediction.tenant_recovery_amount,
            landlord_recovery_amount=prediction.landlord_recovery_amount,
            predicted_settlement_range=settlement_range,
            issue_predictions=issue_preds,
            key_strengths=prediction.key_strengths,
            key_weaknesses=prediction.key_weaknesses,
            uncertainties=prediction.uncertainties,
            retrieved_cases=prediction.retrieved_cases,
            total_cases_analyzed=prediction.total_cases_analyzed,
            reasoning_trace=reasoning_trace,
            disclaimer=prediction.disclaimer,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{prediction_id}")
async def get_prediction(
    prediction_id: str,
    prediction_service: PredictionService = Depends(get_prediction_service),
):
    """
    Retrieve a previously generated prediction.
    """
    try:
        prediction = await prediction_service.get_prediction(prediction_id)

        if not prediction:
            raise HTTPException(status_code=404, detail=f"Prediction not found: {prediction_id}")

        return prediction
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/case/{case_id}")
async def get_predictions_for_case(
    case_id: str,
    prediction_service: PredictionService = Depends(get_prediction_service),
):
    """
    List all predictions for a case.
    """
    try:
        predictions = await prediction_service.list_predictions_for_case(case_id)
        return {"case_id": case_id, "predictions": predictions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
