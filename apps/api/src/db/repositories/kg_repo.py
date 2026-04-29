from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.models import KGEdgeRow, KGNodeRow, KnowledgeGraphRow
from packages.kg_builder.models.edges import Edge
from packages.kg_builder.models.graph import KnowledgeGraph
from packages.kg_builder.models.nodes import (
    BaseNode,
    ClaimedAmountNode,
    EventNode,
    EvidenceNode,
    IssueNode,
    LeaseNode,
    PartyNode,
    PropertyNode,
)
from packages.kg_builder.storage.graph_serialization import (
    deserialize_knowledge_graph,
    serialize_knowledge_graph,
    serialize_node,
)


_NODE_CLASSES = {
    "party": PartyNode,
    "property": PropertyNode,
    "lease": LeaseNode,
    "evidence": EvidenceNode,
    "event": EventNode,
    "issue": IssueNode,
    "claimed_amount": ClaimedAmountNode,
}


def _parse_event_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


class KnowledgeGraphRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def save(self, kg: KnowledgeGraph) -> None:
        payload = serialize_knowledge_graph(kg)
        meta_section = payload.get("metadata")
        # Use the Python attr name "metadata_" for pg_insert values (ORM resolves
        # it to the "metadata" column). The excluded[] dict in on_conflict_do_update
        # uses actual SQL column names, so we map "metadata_" -> "metadata" there.
        values = dict(
            case_id=kg.case_id,
            graph_id=kg.graph_id,
            created_at=kg.created_at,
            updated_at=payload.get("updated_at"),
            validation_errors=payload.get("validation_errors"),
            validation_warnings=payload.get("validation_warnings"),
            validation_info=payload.get("validation_info"),
            is_consistent=payload.get("is_consistent"),
            data_quality_tier=payload.get("data_quality_tier"),
            metadata_=meta_section,
            payload=payload,
        )
        col_name_map = {"metadata_": "metadata"}
        stmt = pg_insert(KnowledgeGraphRow).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[KnowledgeGraphRow.case_id],
            set_={
                col_name_map.get(k, k): stmt.excluded[col_name_map.get(k, k)]
                for k in values if k != "case_id"
            },
        )
        await self._s.execute(stmt)

        await self._s.execute(delete(KGEdgeRow).where(KGEdgeRow.case_id == kg.case_id))
        await self._s.execute(delete(KGNodeRow).where(KGNodeRow.case_id == kg.case_id))

        for node in kg.nodes:
            d = serialize_node(node)
            type_str = node.node_type.value if hasattr(node.node_type, "value") else node.node_type
            self._s.add(KGNodeRow(
                case_id=kg.case_id,
                node_id=node.node_id,
                node_type=type_str,
                confidence=float(node.confidence),
                source=node.source,
                source_text=getattr(node, "source_text", None),
                created_at=getattr(node, "created_at", None) or kg.created_at,
                event_date=_parse_event_date(d.get("event_date")),
                amount=d.get("amount") if type_str == "claimed_amount" else None,
                node_data=d,
                metadata_=d.get("metadata"),
            ))

        # Flush nodes before inserting edges so FK constraints are satisfied.
        await self._s.flush()

        for edge in kg.edges:
            d = edge.model_dump(mode="json")
            self._s.add(KGEdgeRow(
                case_id=kg.case_id,
                edge_id=edge.edge_id,
                edge_type=edge.edge_type.value,
                source_node_id=edge.source_node_id,
                target_node_id=edge.target_node_id,
                confidence=float(edge.confidence),
                source=edge.source,
                description=edge.description,
                metadata_=d.get("metadata"),
                payload=d,
            ))

    async def get(self, case_id: str) -> Optional[KnowledgeGraph]:
        row = await self._s.get(KnowledgeGraphRow, case_id)
        if row is None:
            return None
        nodes_q = await self._s.execute(
            select(KGNodeRow).where(KGNodeRow.case_id == case_id)
        )
        edges_q = await self._s.execute(
            select(KGEdgeRow).where(KGEdgeRow.case_id == case_id)
        )
        # Sort by ID for deterministic round-trip ordering.
        node_rows = sorted(nodes_q.scalars(), key=lambda n: n.node_id)
        edge_rows = sorted(edges_q.scalars(), key=lambda e: e.edge_id)
        kg_dict = dict(row.payload)
        kg_dict["nodes"] = [n.node_data for n in node_rows]
        kg_dict["edges"] = [e.payload for e in edge_rows]
        return deserialize_knowledge_graph(kg_dict)

    async def delete(self, case_id: str) -> None:
        row = await self._s.get(KnowledgeGraphRow, case_id)
        if row:
            await self._s.delete(row)

    async def list_case_ids(self) -> list[str]:
        result = await self._s.execute(select(KnowledgeGraphRow.case_id))
        return [r for (r,) in result.all()]
