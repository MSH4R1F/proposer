from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.models import IntakeSessionRow
from apps.api.src.db.repositories._domain_meta import (
    extract_domain_block as _extract_domain_block,
)
from packages.llm_orchestrator.models.conversation import ConversationState


@dataclass(frozen=True)
class VersionedConversationState:
    state: ConversationState
    version: int


class ConcurrentUpdateError(RuntimeError):
    pass


class SessionsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def save(self, state: ConversationState, *, expected_version: Optional[int] = None) -> None:
        payload = state.model_dump(mode="json")
        domain = _extract_domain_block(payload)
        values = dict(
            session_id=state.session_id,
            case_id=state.case_file.case_id,
            user_role=(state.case_file.user_role.value
                       if state.case_file.user_role else None),
            current_stage=state.current_stage.value,
            started_at=state.started_at,
            updated_at=state.updated_at,
            intake_complete=bool(state.case_file.intake_complete),
            completeness_score=float(state.case_file.completeness_score or 0.0),
            role_explicitly_set=bool(state.role_explicitly_set),
            domain_id=domain["domain_id"],
            domain_version=domain["domain_version"],
            matter_types=domain["matter_types"],
            routing_confidence=domain["routing_confidence"],
            routing_metadata=domain["routing_metadata"],
            payload=payload,
        )
        if expected_version is not None:
            result = await self._s.execute(
                update(IntakeSessionRow)
                .where(
                    IntakeSessionRow.session_id == state.session_id,
                    IntakeSessionRow.version == expected_version,
                )
                .values(**values, version=IntakeSessionRow.version + 1)
            )
            if result.rowcount != 1:
                raise ConcurrentUpdateError(f"session changed: {state.session_id}")
            return

        stmt = pg_insert(IntakeSessionRow).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[IntakeSessionRow.session_id],
            set_={**{k: stmt.excluded[k] for k in values if k != "session_id"},
                  "version": IntakeSessionRow.version + 1},
        )
        await self._s.execute(stmt)

    async def get(self, session_id: str) -> Optional[ConversationState]:
        row = await self._s.get(IntakeSessionRow, session_id)
        return ConversationState.model_validate(row.payload) if row else None

    async def get_with_version(self, session_id: str) -> Optional[VersionedConversationState]:
        row = await self._s.get(IntakeSessionRow, session_id)
        if row is None:
            return None
        return VersionedConversationState(
            state=ConversationState.model_validate(row.payload),
            version=row.version,
        )

    async def get_by_case_id(self, case_id: str) -> Optional[ConversationState]:
        result = await self._s.execute(
            select(IntakeSessionRow).where(IntakeSessionRow.case_id == case_id)
        )
        row = result.scalar_one_or_none()
        return ConversationState.model_validate(row.payload) if row else None

    async def delete(self, session_id: str) -> None:
        row = await self._s.get(IntakeSessionRow, session_id)
        if row:
            await self._s.delete(row)

    async def list_all(self) -> list[ConversationState]:
        result = await self._s.execute(select(IntakeSessionRow))
        return [ConversationState.model_validate(r.payload) for r in result.scalars()]
