from __future__ import annotations

from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.models import EvidenceMetadataRow
from packages.llm_orchestrator.models.evidence import EvidenceMetadata


class EvidenceRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def save(self, metadata: EvidenceMetadata) -> None:
        payload = metadata.model_dump(mode="json")
        values = dict(
            case_id=metadata.case_id,
            evidence_id=metadata.evidence_id,
            evidence_type=(
                metadata.evidence_type.value
                if hasattr(metadata.evidence_type, "value")
                else metadata.evidence_type
            ),
            file_url=metadata.file_url,
            storage_path=metadata.storage_path,
            file_name=metadata.file_name,
            file_type=metadata.file_type,
            description=metadata.description,
            extracted_text=metadata.extracted_text,
            image_description=metadata.image_description,
            payload=payload,
        )
        stmt = pg_insert(EvidenceMetadataRow).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[EvidenceMetadataRow.case_id, EvidenceMetadataRow.evidence_id],
            set_={k: stmt.excluded[k] for k in values
                  if k not in ("case_id", "evidence_id")},
        )
        await self._s.execute(stmt)

    async def get(self, case_id: str, evidence_id: str) -> Optional[EvidenceMetadata]:
        row = await self._s.get(EvidenceMetadataRow, (case_id, evidence_id))
        return EvidenceMetadata.model_validate(row.payload) if row else None

    async def get_by_case_id(self, case_id: str) -> list[EvidenceMetadata]:
        result = await self._s.execute(
            select(EvidenceMetadataRow).where(EvidenceMetadataRow.case_id == case_id)
        )
        return [EvidenceMetadata.model_validate(r.payload) for r in result.scalars()]

    async def delete(self, case_id: str, evidence_id: str) -> None:
        await self._s.execute(
            delete(EvidenceMetadataRow).where(
                EvidenceMetadataRow.case_id == case_id,
                EvidenceMetadataRow.evidence_id == evidence_id,
            )
        )
