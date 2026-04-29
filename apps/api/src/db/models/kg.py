from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import Boolean, Date, ForeignKeyConstraint, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.src.db.base import Base
from apps.api.src.db.models._enums import edge_type_enum, node_type_enum


class KnowledgeGraphRow(Base):
    __tablename__ = "knowledge_graphs"

    case_id: Mapped[str] = mapped_column(String, primary_key=True)
    graph_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    validation_errors: Mapped[Optional[list[Any]]] = mapped_column(JSONB, nullable=True)
    validation_warnings: Mapped[Optional[list[Any]]] = mapped_column(JSONB, nullable=True)
    validation_info: Mapped[Optional[list[Any]]] = mapped_column(JSONB, nullable=True)
    is_consistent: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    data_quality_tier: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata", JSONB, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class KGNodeRow(Base):
    __tablename__ = "kg_nodes"

    case_id: Mapped[str] = mapped_column(String, primary_key=True)
    node_id: Mapped[str] = mapped_column(String, primary_key=True)
    node_type: Mapped[str] = mapped_column(node_type_enum, nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    source_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    event_date: Mapped[Optional[str]] = mapped_column(Date, nullable=True)
    amount: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    node_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata", JSONB, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(["case_id"], ["knowledge_graphs.case_id"], ondelete="CASCADE"),
    )


class KGEdgeRow(Base):
    __tablename__ = "kg_edges"

    case_id: Mapped[str] = mapped_column(String, primary_key=True)
    edge_id: Mapped[str] = mapped_column(String, primary_key=True)
    edge_type: Mapped[str] = mapped_column(edge_type_enum, nullable=False)
    source_node_id: Mapped[str] = mapped_column(String, nullable=False)
    target_node_id: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata", JSONB, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["case_id", "source_node_id"],
            ["kg_nodes.case_id", "kg_nodes.node_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["case_id", "target_node_id"],
            ["kg_nodes.case_id", "kg_nodes.node_id"],
            ondelete="CASCADE",
        ),
    )
