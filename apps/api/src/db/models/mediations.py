from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.src.db.base import Base
from apps.api.src.db.models._enums import (
    mediation_status_enum, message_type_enum, offer_status_enum, party_role_enum,
)


class MediationSessionRow(Base):
    __tablename__ = "mediations"

    mediation_id: Mapped[str] = mapped_column(String, primary_key=True)
    dispute_id: Mapped[str] = mapped_column(
        String, ForeignKey("disputes.dispute_id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    status: Mapped[str] = mapped_column(mediation_status_enum, nullable=False)
    started_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    settled_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    settlement_amount: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    escalated_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class MediationMessageRow(Base):
    __tablename__ = "mediation_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mediation_id: Mapped[str] = mapped_column(
        String, ForeignKey("mediations.mediation_id", ondelete="CASCADE"), nullable=False,
    )
    message_id: Mapped[str] = mapped_column(String, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    # May be "tenant", "landlord", or "ai_mediator"; keep as String, not party_role_enum.
    sender_role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(message_type_enum, nullable=False)
    timestamp: Mapped[str] = mapped_column(Text, nullable=False)
    offer_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata", JSONB, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        UniqueConstraint("mediation_id", "message_id", name="uq_mediation_messages_message_id"),
        UniqueConstraint("mediation_id", "ordinal", name="uq_mediation_messages_med_ordinal"),
        ForeignKeyConstraint(
            ["mediation_id", "offer_id"],
            ["structured_offers.mediation_id", "structured_offers.offer_id"],
        ),
        Index("ix_mediation_messages_med_ordinal", "mediation_id", "ordinal"),
        Index("ix_mediation_messages_med_ts", "mediation_id", "timestamp"),
        Index("ix_mediation_messages_offer", "offer_id"),
    )


class StructuredOfferRow(Base):
    __tablename__ = "structured_offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mediation_id: Mapped[str] = mapped_column(
        String, ForeignKey("mediations.mediation_id", ondelete="CASCADE"), nullable=False,
    )
    offer_id: Mapped[str] = mapped_column(String, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric, nullable=False)
    proposed_by_role: Mapped[str] = mapped_column(party_role_enum, nullable=False)
    status: Mapped[str] = mapped_column(offer_status_enum, nullable=False)
    proposed_at: Mapped[str] = mapped_column(Text, nullable=False)
    responded_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    counter_amount: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        UniqueConstraint("mediation_id", "offer_id", name="uq_structured_offers_offer_id"),
        UniqueConstraint("mediation_id", "ordinal", name="uq_structured_offers_med_ordinal"),
        CheckConstraint("amount >= 0", name="ck_structured_offers_amount_nonnegative"),
        Index("ix_offers_med_ordinal", "mediation_id", "ordinal"),
        Index("ix_offers_med_status", "mediation_id", "status"),
    )
