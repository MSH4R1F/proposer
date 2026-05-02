from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.src.db.base import Base
from apps.api.src.db.models._enums import dispute_status_enum, party_role_enum


class DisputeRow(Base):
    __tablename__ = "disputes"

    dispute_id: Mapped[str] = mapped_column(String, primary_key=True)
    invite_code: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(dispute_status_enum, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_role: Mapped[Optional[str]] = mapped_column(party_role_enum, nullable=True)
    tenant_session_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("intake_sessions.session_id", ondelete="SET NULL"), nullable=True,
    )
    landlord_session_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("intake_sessions.session_id", ondelete="SET NULL"), nullable=True,
    )
    property_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    property_postcode: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    deposit_amount: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    cached_prediction_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("predictions.prediction_id", ondelete="SET NULL"), nullable=True,
    )
    prediction_cache_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # SHA-124 phase 2: domain routing metadata. NOT NULL after revision 0003.
    domain_id: Mapped[str] = mapped_column(
        Text, nullable=False, default="housing.deposit.v1",
        server_default="housing.deposit.v1",
    )
    domain_version: Mapped[str] = mapped_column(
        Text, nullable=False, default="v1", server_default="v1",
    )
    # forum stays NULL — Phase 0 audit explicitly forbids guessing it for legacy rows.
    forum: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    matter_types: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]",
    )
    routing_confidence: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    routing_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}",
    )

    __table_args__ = (
        Index("ix_disputes_domain_forum", "domain_id", "forum"),
    )
