import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.repositories.predictions_repo import PredictionsRepo
from packages.llm_orchestrator.models.prediction_v2 import (
    PredictionResult, IssuePrediction, ReasoningStep, Citation,
    OutcomeType, IssueOutcome, IssueType, EvidenceStrength,
)


def _make_prediction(prediction_id: str = "p1", case_id: str = "c1") -> PredictionResult:
    citation = Citation(
        case_reference="LON/00AY/2023/0042", year=2023, region="London",
        paragraph="12", quote="Q" * 80, relevance="R" * 80,
        similarity_score=0.91, verified=True,
    )
    issue = IssuePrediction(
        issue_type=IssueType.CLEANING, issue_description="Dirty kitchen",
        outcome=IssueOutcome.LANDLORD_WINS, raw_confidence=0.7,
        predicted_amount=120.0, amount_range=(80.0, 160.0),
        reasoning="Inventory checkin clean, checkout dirty.",
        key_factors=["clear inventory"], supporting_cases=[citation],
        counterfactuals=[], evidence_strength=EvidenceStrength.MODERATE,
    )
    step = ReasoningStep(
        step_number=1, category="legal_framework",
        title="Deposit framework", content="Long content about prescribed info...",
        citations=[citation], confidence=0.8,
    )
    return PredictionResult(
        case_id=case_id, prediction_id=prediction_id,
        timestamp="2026-01-01T00:00:00",
        overall_outcome=OutcomeType.SPLIT, overall_confidence=0.65,
        outcome_summary="Mixed outcome",
        tenant_recovery_amount=400.0, landlord_recovery_amount=120.0,
        predicted_settlement_range=(380.0, 500.0),
        issue_predictions=[issue], reasoning_trace=[step],
        retrieved_cases=[], total_cases_analyzed=42,
        # pipeline_metadata field expects Optional[PipelineMetadata], not a plain dict;
        # set to None to avoid Pydantic validation failure on field-name mismatch.
        pipeline_metadata=None,
        temporal_distribution={2023: 12, 2022: 10},
        key_strengths=["clear evidence"], key_weaknesses=[],
        uncertainties=[], missing_information=[],
        model_version="2.0.0", pipeline_version="v2",
    )


@pytest.mark.asyncio
async def test_prediction_roundtrip_with_children(db_session: AsyncSession) -> None:
    repo = PredictionsRepo(db_session)
    p = _make_prediction()
    await repo.save(p)
    await db_session.commit()
    loaded = await repo.get(p.prediction_id)
    assert loaded is not None
    assert loaded.model_dump(mode="json") == p.model_dump(mode="json")


@pytest.mark.asyncio
async def test_save_replaces_children_on_upsert(db_session: AsyncSession) -> None:
    repo = PredictionsRepo(db_session)
    p = _make_prediction()
    await repo.save(p)
    await db_session.commit()

    p.issue_predictions = []
    await repo.save(p)
    await db_session.commit()

    loaded = await repo.get(p.prediction_id)
    assert loaded is not None
    assert loaded.issue_predictions == []


@pytest.mark.asyncio
async def test_get_by_case_id_returns_only_matching(db_session: AsyncSession) -> None:
    repo = PredictionsRepo(db_session)
    p1 = _make_prediction(prediction_id="p1", case_id="case-A")
    p2 = _make_prediction(prediction_id="p2", case_id="case-B")
    await repo.save(p1)
    await repo.save(p2)
    await db_session.commit()
    listed = await repo.get_by_case_id("case-A")
    assert {p.prediction_id for p in listed} == {"p1"}
