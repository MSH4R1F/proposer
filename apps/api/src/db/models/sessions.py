from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import Boolean, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.src.db.base import Base
from apps.api.src.db.models._enums import intake_stage_enum, user_role_enum


class IntakeSessionRow(Base):
    __tablename__ = "intake_sessions"

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    user_role: Mapped[Optional[str]] = mapped_column(user_role_enum, nullable=True)
    current_stage: Mapped[str] = mapped_column(intake_stage_enum, nullable=False)
    started_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    intake_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    completeness_score: Mapped[float] = mapped_column(Numeric, nullable=False, default=0.0)
    role_explicitly_set: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
