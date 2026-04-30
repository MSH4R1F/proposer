from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from apps.api.src.routers.predictions import (
    PredictionRequest,
    generate_prediction,
    get_prediction as get_prediction_route,
)
from apps.api.src.services.prediction_service import PredictionCacheConflictError
from packages.llm_orchestrator.models.prediction_v2 import (
    Citation,
    EvidenceStrength,
    IssueOutcome,
    IssuePrediction,
    IssueType,
    OutcomeType,
    PredictionResult,
    ReasoningStep,
)


def _make_prediction() -> PredictionResult:
    citation = Citation(
        case_reference="LON/00AY/2023/0042",
        year=2023,
        region="London",
        paragraph="12",
        quote="Q" * 80,
        relevance="R" * 80,
        similarity_score=0.91,
        verified=True,
    )
    issue = IssuePrediction(
        issue_type=IssueType.CLEANING,
        issue_description="Dirty kitchen",
        outcome=IssueOutcome.LANDLORD_WINS,
        raw_confidence=0.7,
        predicted_amount=120.0,
        amount_range=(80.0, 160.0),
        reasoning="Inventory check-in clean, checkout dirty.",
        key_factors=["clear inventory"],
        supporting_cases=[citation],
        counterfactuals=[],
        evidence_strength=EvidenceStrength.MODERATE,
    )
    step = ReasoningStep(
        step_number=1,
        category="legal_framework",
        title="Deposit framework",
        content="Long content...",
        citations=[citation],
        confidence=0.8,
    )
    return PredictionResult(
        case_id="case-1",
        prediction_id="pred-1",
        overall_outcome=OutcomeType.SPLIT,
        overall_confidence=0.65,
        outcome_summary="Mixed outcome",
        tenant_recovery_amount=400.0,
        landlord_recovery_amount=120.0,
        predicted_settlement_range=(380.0, 500.0),
        issue_predictions=[issue],
        reasoning_trace=[step],
        retrieved_cases=[],
        total_cases_analyzed=42,
        key_strengths=["clear evidence"],
        key_weaknesses=[],
        uncertainties=[],
    )


@pytest.mark.asyncio
async def test_generate_prediction_response_preserves_frontend_issue_shape() -> None:
    prediction = _make_prediction()
    service = AsyncMock()
    service.check_case_ready.return_value = {
        "exists": True,
        "is_complete": True,
        "completeness": 1.0,
        "missing_info": [],
    }
    service.generate_prediction.return_value = prediction

    response = await generate_prediction(
        PredictionRequest(case_id="case-1"),
        prediction_service=service,
    )

    issue = response.issue_predictions[0]
    assert issue.issue_description == "Dirty kitchen"
    assert issue.predicted_outcome == "landlord_wins"
    assert issue.confidence == 0.7
    assert issue.predicted_amount == 120.0
    assert issue.amount_range == [80.0, 160.0]
    assert issue.supporting_cases[0]["case_reference"] == "LON/00AY/2023/0042"
    assert response.reasoning_trace is not None
    assert response.reasoning_trace[0]["confidence"] == 0.8


@pytest.mark.asyncio
async def test_get_prediction_response_uses_same_frontend_issue_shape() -> None:
    prediction = _make_prediction()
    service = AsyncMock()
    service.get_prediction.return_value = prediction.model_dump(mode="json")

    response = await get_prediction_route("pred-1", prediction_service=service)

    issue = response.issue_predictions[0]
    assert issue.issue_description == "Dirty kitchen"
    assert issue.predicted_outcome == "landlord_wins"
    assert issue.confidence == 0.7
    assert issue.predicted_amount == 120.0
    assert issue.amount_range == [80.0, 160.0]
    assert issue.supporting_cases[0]["case_reference"] == "LON/00AY/2023/0042"


@pytest.mark.asyncio
async def test_generate_prediction_cache_conflict_returns_409() -> None:
    service = AsyncMock()
    service.check_case_ready.return_value = {
        "exists": True,
        "is_complete": True,
        "completeness": 1.0,
        "missing_info": [],
    }
    service.generate_prediction.side_effect = PredictionCacheConflictError("retry")

    with pytest.raises(HTTPException) as exc:
        await generate_prediction(
            PredictionRequest(case_id="case-1"),
            prediction_service=service,
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == "retry"
