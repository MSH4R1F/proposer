from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.models import DisputeRow
from apps.api.src.db.repositories._domain_meta import (
    extract_domain_block as _extract_domain_block,
    extract_forum as _extract_forum,
)
from apps.api.src.db.repositories.sessions_repo import ConcurrentUpdateError
from llm_orchestrator.models.dispute import DisputeCase


@dataclass(frozen=True)
class LockedDisputeForPredictionCache:
    dispute: DisputeCase
    cached_prediction_id: Optional[str]
    prediction_cache_key: Optional[str]


@dataclass(frozen=True)
class VersionedDisputeCase:
    dispute: DisputeCase
    version: int


class DisputesRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    @staticmethod
    def _row_to_dispute(row: DisputeRow) -> DisputeCase:
        payload = dict(row.payload)
        payload.update(
            dispute_id=row.dispute_id,
            invite_code=row.invite_code,
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
            created_by_role=(
                row.created_by_role
                if row.created_by_role is not None
                else payload.get("created_by_role")
            ),
            tenant_session_id=row.tenant_session_id,
            landlord_session_id=row.landlord_session_id,
            property_address=row.property_address,
            property_postcode=row.property_postcode,
            deposit_amount=(
                float(row.deposit_amount)
                if isinstance(row.deposit_amount, Decimal)
                else row.deposit_amount
            ),
        )
        return DisputeCase.model_validate(payload)

    async def save(self, dispute: DisputeCase, *, expected_version: Optional[int] = None) -> None:
        payload = dispute.model_dump(mode="json")
        domain = _extract_domain_block(payload)
        values = dict(
            dispute_id=dispute.dispute_id,
            invite_code=dispute.invite_code,
            status=dispute.status.value,
            created_at=dispute.created_at,
            updated_at=dispute.updated_at,
            created_by_role=(dispute.created_by_role.value
                             if hasattr(dispute.created_by_role, "value")
                             else dispute.created_by_role),
            tenant_session_id=dispute.tenant_session_id,
            landlord_session_id=dispute.landlord_session_id,
            property_address=dispute.property_address,
            property_postcode=dispute.property_postcode,
            deposit_amount=dispute.deposit_amount,
            cached_prediction_id=None,
            prediction_cache_key=None,
            domain_id=domain["domain_id"],
            domain_version=domain["domain_version"],
            forum=_extract_forum(payload),
            matter_types=domain["matter_types"],
            routing_confidence=domain["routing_confidence"],
            routing_metadata=domain["routing_metadata"],
            payload=payload,
        )
        if expected_version is not None:
            result = await self._s.execute(
                update(DisputeRow)
                .where(
                    DisputeRow.dispute_id == dispute.dispute_id,
                    DisputeRow.version == expected_version,
                )
                .values(
                    **{
                        k: v for k, v in values.items()
                        if k not in ("cached_prediction_id", "prediction_cache_key")
                    },
                    version=DisputeRow.version + 1,
                )
            )
            if result.rowcount != 1:
                raise ConcurrentUpdateError(f"dispute changed: {dispute.dispute_id}")
            return

        stmt = pg_insert(DisputeRow).values(**values)
        update_cols = {k: stmt.excluded[k] for k in values
                       if k not in ("dispute_id", "cached_prediction_id", "prediction_cache_key")}
        update_cols["version"] = DisputeRow.version + 1
        stmt = stmt.on_conflict_do_update(
            index_elements=[DisputeRow.dispute_id], set_=update_cols,
        )
        await self._s.execute(stmt)

    async def get(self, dispute_id: str) -> Optional[DisputeCase]:
        row = await self._s.get(DisputeRow, dispute_id)
        return self._row_to_dispute(row) if row else None

    async def get_with_version(self, dispute_id: str) -> Optional[VersionedDisputeCase]:
        row = await self._s.get(DisputeRow, dispute_id)
        if row is None:
            return None
        return VersionedDisputeCase(
            dispute=self._row_to_dispute(row),
            version=row.version,
        )

    async def get_by_invite_code(self, code: str) -> Optional[DisputeCase]:
        result = await self._s.execute(
            select(DisputeRow).where(DisputeRow.invite_code == code)
        )
        row = result.scalar_one_or_none()
        return self._row_to_dispute(row) if row else None

    async def get_by_session_id(self, session_id: str) -> list[DisputeCase]:
        result = await self._s.execute(
            select(DisputeRow).where(
                (DisputeRow.tenant_session_id == session_id)
                | (DisputeRow.landlord_session_id == session_id)
            )
        )
        return [self._row_to_dispute(r) for r in result.scalars()]

    async def lock_by_invite_code(self, code: str) -> Optional[DisputeCase]:
        result = await self._s.execute(
            select(DisputeRow)
            .where(DisputeRow.invite_code == code)
            .with_for_update()
        )
        row = result.scalar_one_or_none()
        return self._row_to_dispute(row) if row else None

    async def lock_by_session_id(self, session_id: str) -> list[DisputeCase]:
        result = await self._s.execute(
            select(DisputeRow)
            .where(
                (DisputeRow.tenant_session_id == session_id)
                | (DisputeRow.landlord_session_id == session_id)
            )
            .with_for_update()
        )
        return [self._row_to_dispute(r) for r in result.scalars()]

    async def lock(self, dispute_id: str) -> Optional[DisputeCase]:
        result = await self._s.execute(
            select(DisputeRow).where(DisputeRow.dispute_id == dispute_id).with_for_update()
        )
        row = result.scalar_one_or_none()
        return self._row_to_dispute(row) if row else None

    async def lock_for_prediction_cache(
        self, dispute_id: str
    ) -> Optional[LockedDisputeForPredictionCache]:
        result = await self._s.execute(
            select(DisputeRow).where(DisputeRow.dispute_id == dispute_id).with_for_update()
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return LockedDisputeForPredictionCache(
            dispute=self._row_to_dispute(row),
            cached_prediction_id=row.cached_prediction_id,
            prediction_cache_key=row.prediction_cache_key,
        )

    async def set_cached_prediction_id(
        self, dispute_id: str, prediction_id: Optional[str], *, cache_key: Optional[str] = None,
    ) -> None:
        result = await self._s.execute(
            update(DisputeRow)
            .where(DisputeRow.dispute_id == dispute_id)
            .values(cached_prediction_id=prediction_id, prediction_cache_key=cache_key)
        )
        if result.rowcount != 1:
            raise ConcurrentUpdateError(f"dispute not found: {dispute_id}")

    async def delete(self, dispute_id: str) -> None:
        row = await self._s.get(DisputeRow, dispute_id)
        if row:
            await self._s.delete(row)

    async def list_all(self) -> list[DisputeCase]:
        result = await self._s.execute(select(DisputeRow))
        return [self._row_to_dispute(r) for r in result.scalars()]
