from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.src.db.base import Base
from apps.api.src.db.models._enums import (
    citation_source_enum, evidence_strength_enum, issue_outcome_enum,
    issue_type_enum, outcome_type_enum,
)


class PredictionRow(Base):
    __tablename__ = "predictions"

    prediction_id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    overall_outcome: Mapped[str] = mapped_column(outcome_type_enum, nullable=False)
    overall_confidence: Mapped[float] = mapped_column(Numeric, nullable=False)
    range_lo: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    range_hi: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    pipeline_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    retrieval_quality: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    rag_confidence: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    pipeline_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    citation_verification: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata", JSONB, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class PredictionIssueRow(Base):
    __tablename__ = "prediction_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prediction_id: Mapped[str] = mapped_column(
        String, ForeignKey("predictions.prediction_id", ondelete="CASCADE"), nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    issue_type: Mapped[str] = mapped_column(issue_type_enum, nullable=False)
    issue_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    outcome: Mapped[str] = mapped_column(issue_outcome_enum, nullable=False)
    raw_confidence: Mapped[float] = mapped_column(Numeric, nullable=False)
    calibrated_confidence: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    predicted_amount: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    amount_range_lo: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    amount_range_hi: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    key_factors: Mapped[Optional[list[Any]]] = mapped_column(JSONB, nullable=True)
    supporting_cases: Mapped[Optional[list[Any]]] = mapped_column(JSONB, nullable=True)
    counterfactuals: Mapped[Optional[list[Any]]] = mapped_column(JSONB, nullable=True)
    evidence_strength: Mapped[Optional[str]] = mapped_column(evidence_strength_enum, nullable=True)
    data_completeness_impact: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class PredictionReasoningStepRow(Base):
    __tablename__ = "prediction_reasoning_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prediction_id: Mapped[str] = mapped_column(
        String, ForeignKey("predictions.prediction_id", ondelete="CASCADE"), nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    step_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class PredictionCitationRow(Base):
    __tablename__ = "prediction_citations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prediction_id: Mapped[str] = mapped_column(
        String, ForeignKey("predictions.prediction_id", ondelete="CASCADE"), nullable=False,
    )
    reasoning_step_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("prediction_reasoning_steps.id", ondelete="CASCADE"), nullable=True,
    )
    citation_source: Mapped[str] = mapped_column(citation_source_enum, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    case_reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    paragraph: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quote: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    relevance: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    similarity_score: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    verified: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
