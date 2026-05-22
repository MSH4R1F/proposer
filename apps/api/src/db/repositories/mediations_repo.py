from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.models import MediationSessionRow, MediationMessageRow, StructuredOfferRow
from apps.api.src.db.repositories._domain_meta import (
    extract_domain_block as _extract_domain_block,
)
from apps.api.src.db.repositories.sessions_repo import ConcurrentUpdateError
from llm_orchestrator.models.mediation import MediationSession


@dataclass(frozen=True)
class VersionedMediationSession:
    session: MediationSession
    version: int


class MediationsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def save(
        self,
        mediation: MediationSession,
        *,
        expected_version: Optional[int] = None,
    ) -> None:
        payload = mediation.model_dump(mode="json")
        domain = _extract_domain_block(payload)
        values = dict(
            mediation_id=mediation.mediation_id,
            dispute_id=mediation.dispute_id,
            status=mediation.status.value,
            started_at=mediation.started_at,
            updated_at=getattr(mediation, "updated_at", None),
            settled_at=getattr(mediation, "settled_at", None),
            settlement_amount=getattr(mediation, "settlement_amount", None),
            escalated_at=getattr(mediation, "escalated_at", None),
            domain_id=domain["domain_id"],
            domain_version=domain["domain_version"],
            payload=payload,
        )

        if expected_version is not None:
            result = await self._s.execute(
                update(MediationSessionRow)
                .where(
                    MediationSessionRow.mediation_id == mediation.mediation_id,
                    MediationSessionRow.version == expected_version,
                )
                .values(**values, version=MediationSessionRow.version + 1)
            )
            if result.rowcount != 1:
                raise ConcurrentUpdateError(
                    f"mediation changed or not found: {mediation.mediation_id}"
                )
        else:
            stmt = pg_insert(MediationSessionRow).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[MediationSessionRow.mediation_id],
                set_={
                    k: stmt.excluded[k]
                    for k in values
                    if k != "mediation_id"
                } | {"version": MediationSessionRow.version + 1},
            )
            await self._s.execute(stmt)

        await self._s.flush()

        # Replace children
        await self._s.execute(
            delete(MediationMessageRow).where(
                MediationMessageRow.mediation_id == mediation.mediation_id
            )
        )
        await self._s.execute(
            delete(StructuredOfferRow).where(
                StructuredOfferRow.mediation_id == mediation.mediation_id
            )
        )

        # Insert offers first so offer-linked messages satisfy the composite FK.
        for i, offer in enumerate(getattr(mediation, "offers", []) or []):
            od = offer.model_dump(mode="json")
            self._s.add(StructuredOfferRow(
                mediation_id=mediation.mediation_id,
                offer_id=offer.id,
                ordinal=i,
                amount=float(offer.amount),
                proposed_by_role=(
                    offer.proposed_by_role.value
                    if hasattr(offer.proposed_by_role, "value")
                    else offer.proposed_by_role
                ),
                status=offer.status.value,
                proposed_at=offer.proposed_at,
                responded_at=getattr(offer, "responded_at", None),
                counter_amount=(
                    float(offer.counter_amount)
                    if getattr(offer, "counter_amount", None) is not None
                    else None
                ),
                payload=od,
            ))

        await self._s.flush()

        # Insert messages
        for i, msg in enumerate(getattr(mediation, "messages", []) or []):
            md = msg.model_dump(mode="json")
            self._s.add(MediationMessageRow(
                mediation_id=mediation.mediation_id,
                message_id=msg.id,
                ordinal=i,
                sender_role=msg.sender_role,
                content=msg.content,
                message_type=msg.message_type.value,
                timestamp=msg.timestamp,
                offer_id=getattr(msg, "offer_id", None),
                metadata_=md.get("metadata"),
                payload=md,
            ))

    async def get(self, mediation_id: str) -> Optional[MediationSession]:
        row = await self._s.get(MediationSessionRow, mediation_id)
        return MediationSession.model_validate(row.payload) if row else None

    async def get_with_version(
        self, mediation_id: str
    ) -> Optional[VersionedMediationSession]:
        row = await self._s.get(MediationSessionRow, mediation_id)
        if row is None:
            return None
        return VersionedMediationSession(
            session=MediationSession.model_validate(row.payload),
            version=row.version,
        )

    async def lock(
        self, mediation_id: str
    ) -> Optional[VersionedMediationSession]:
        result = await self._s.execute(
            select(MediationSessionRow)
            .where(MediationSessionRow.mediation_id == mediation_id)
            .with_for_update()
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return VersionedMediationSession(
            session=MediationSession.model_validate(row.payload),
            version=row.version,
        )

    async def get_by_dispute_id(self, dispute_id: str) -> Optional[MediationSession]:
        result = await self._s.execute(
            select(MediationSessionRow).where(
                MediationSessionRow.dispute_id == dispute_id
            )
        )
        row = result.scalar_one_or_none()
        return MediationSession.model_validate(row.payload) if row else None

    async def lock_by_dispute_id(
        self, dispute_id: str
    ) -> Optional[VersionedMediationSession]:
        result = await self._s.execute(
            select(MediationSessionRow)
            .where(MediationSessionRow.dispute_id == dispute_id)
            .with_for_update()
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return VersionedMediationSession(
            session=MediationSession.model_validate(row.payload),
            version=row.version,
        )

    async def delete(self, mediation_id: str) -> None:
        row = await self._s.get(MediationSessionRow, mediation_id)
        if row:
            await self._s.delete(row)
