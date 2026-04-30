"""
Dispute service.

Manages dispute cases that link tenant and landlord sessions.
Persistence is routed through a UnitOfWork backed by Postgres (Phase 6.2).
"""

from typing import List, Optional

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llm_orchestrator.models.dispute import DisputeCase, DisputeStatus, generate_invite_code
from apps.api.src.db.uow import UnitOfWork

logger = structlog.get_logger()

# Global service instance (legacy singleton — kept for rollback compatibility)
_dispute_service: Optional["DisputeService"] = None

_MAX_INVITE_CODE_RETRIES = 5


class DisputeService:
    """
    Service for managing dispute cases.

    Handles dispute creation, invite code validation, and linking sessions.
    All reads/writes go through a UnitOfWork backed by Postgres.
    """

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        """
        Initialise the dispute service.

        Args:
            sessionmaker: SQLAlchemy async sessionmaker bound to the app engine.
        """
        logger.debug("initializing_dispute_service")
        self._sm = sessionmaker
        logger.info("dispute_service_initialized")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_dispute(
        self,
        session_id: Optional[str] = None,
        role: Optional[str] = None,
        property_address: Optional[str] = None,
        property_postcode: Optional[str] = None,
        deposit_amount: Optional[float] = None,
    ) -> DisputeCase:
        """
        Create a new dispute case.

        Args:
            session_id: Optional session ID of the party creating the dispute
            role: Optional role of the creator ("tenant" or "landlord")
            property_address: Optional property address
            property_postcode: Optional postcode
            deposit_amount: Optional deposit amount

        Returns:
            The created DisputeCase
        """
        logger.debug("creating_dispute", session_id=session_id, role=role)

        _VALID_ROLES = {"tenant", "landlord"}
        if role is not None and role not in _VALID_ROLES:
            raise ValueError(f"Invalid role: {role!r}; expected 'tenant' or 'landlord'")

        # Build the dispute once; override its invite_code explicitly on every
        # attempt so that the module-level `generate_invite_code` symbol is the
        # one called (this allows tests to monkeypatch it on this module).
        dispute = DisputeCase(
            created_by_role=role,
            property_address=property_address,
            property_postcode=property_postcode,
            deposit_amount=deposit_amount,
        )

        # Link the creator's session if provided
        if session_id and role:
            if role == "tenant":
                dispute.link_tenant_session(session_id)
                dispute.status = DisputeStatus.WAITING_FOR_LANDLORD
            else:
                dispute.link_landlord_session(session_id)
                dispute.status = DisputeStatus.WAITING_FOR_TENANT

        for attempt in range(_MAX_INVITE_CODE_RETRIES):
            # Always call our own module-level generate_invite_code so
            # monkeypatching apps.api.src.services.dispute_service works.
            dispute.invite_code = generate_invite_code()

            try:
                async with UnitOfWork(self._sm) as uow:
                    # Check uniqueness first (optimistic path; Postgres unique index is the real guard)
                    existing = await uow.disputes.get_by_invite_code(dispute.invite_code)
                    if existing is not None:
                        logger.debug(
                            "invite_code_collision_check",
                            code=dispute.invite_code,
                            attempt=attempt,
                        )
                        continue
                    await uow.disputes.save(dispute)
            except IntegrityError:
                # Lost the race with another writer — regenerate and retry
                logger.debug(
                    "invite_code_integrity_error_retry",
                    code=dispute.invite_code,
                    attempt=attempt,
                )
                continue

            logger.info(
                "dispute_created",
                dispute_id=dispute.dispute_id,
                invite_code=dispute.invite_code,
                created_by=role,
            )
            return dispute

        raise RuntimeError(
            f"Could not generate a unique invite code after {_MAX_INVITE_CODE_RETRIES} attempts"
        )

    async def get_dispute(self, dispute_id: str) -> Optional[DisputeCase]:
        """Get a dispute by ID."""
        async with UnitOfWork(self._sm) as uow:
            return await uow.disputes.get(dispute_id)

    async def get_dispute_by_invite_code(self, invite_code: str) -> Optional[DisputeCase]:
        """Get a dispute by invite code (case-insensitive, strips whitespace)."""
        normalized_code = invite_code.upper().strip()
        async with UnitOfWork(self._sm) as uow:
            return await uow.disputes.get_by_invite_code(normalized_code)

    async def get_dispute_by_session(self, session_id: str) -> Optional[DisputeCase]:
        """Get a dispute by one of its linked session IDs (returns the first match)."""
        async with UnitOfWork(self._sm) as uow:
            results = await uow.disputes.get_by_session_id(session_id)
        return results[0] if results else None

    async def join_dispute(
        self,
        invite_code: str,
        session_id: str,
        role: str,
    ) -> Optional[DisputeCase]:
        """
        Join an existing dispute using an invite code.

        Args:
            invite_code: The invite code to join with
            session_id: The session ID of the joining party
            role: The role of the joining party ("tenant" or "landlord")

        Returns:
            The updated DisputeCase, or None if join failed
        """
        logger.debug("joining_dispute", invite_code=invite_code, session_id=session_id, role=role)

        _VALID_ROLES = {"tenant", "landlord"}
        if role not in _VALID_ROLES:
            raise ValueError(f"Invalid role: {role!r}; expected 'tenant' or 'landlord'")

        normalized_code = invite_code.upper().strip()

        async with UnitOfWork(self._sm) as uow:
            dispute = await uow.disputes.lock_by_invite_code(normalized_code)
            if not dispute:
                logger.warning("dispute_not_found_for_code", invite_code=invite_code)
                return None

            if role == "tenant":
                if dispute.tenant_session_id:
                    logger.warning("tenant_already_joined", dispute_id=dispute.dispute_id)
                    return None
                dispute.link_tenant_session(session_id)
            else:
                if dispute.landlord_session_id:
                    logger.warning("landlord_already_joined", dispute_id=dispute.dispute_id)
                    return None
                dispute.link_landlord_session(session_id)

            await uow.disputes.save(dispute)

        logger.info(
            "party_joined_dispute",
            dispute_id=dispute.dispute_id,
            role=role,
            session_id=session_id,
        )
        return dispute

    async def update_dispute_from_session(
        self,
        session_id: str,
        property_address: Optional[str] = None,
        property_postcode: Optional[str] = None,
        deposit_amount: Optional[float] = None,
        intake_complete: bool = False,
        role: Optional[str] = None,
    ) -> Optional[DisputeCase]:
        """
        Update dispute info from a session's case file.

        Called when session data changes to keep dispute in sync.
        Uses robust status recalculation to fix any inconsistencies.
        """
        async with UnitOfWork(self._sm) as uow:
            results = await uow.disputes.lock_by_session_id(session_id)
            if not results:
                return None

            dispute = results[0]

            # Update shared property info (first one wins)
            if property_address and not dispute.property_address:
                dispute.property_address = property_address
            if property_postcode and not dispute.property_postcode:
                dispute.property_postcode = property_postcode
            if deposit_amount and not dispute.deposit_amount:
                dispute.deposit_amount = deposit_amount

            # Update completion status using idempotent method
            if intake_complete and role:
                dispute.mark_party_complete(role)
                logger.info(
                    "dispute_party_marked_complete",
                    dispute_id=dispute.dispute_id,
                    role=role,
                    new_status=dispute.status.value,
                    is_ready=dispute.is_ready_for_prediction,
                )

            dispute.update_timestamp()
            await uow.disputes.save(dispute)

        return dispute

    async def sync_dispute_status_from_sessions(
        self,
        dispute_id: str,
        tenant_complete: bool,
        landlord_complete: bool,
    ) -> Optional[DisputeCase]:
        """
        Sync dispute status based on actual session completion data.

        This fixes disputes that may be stuck in incorrect states.
        """
        async with UnitOfWork(self._sm) as uow:
            dispute = await uow.disputes.get(dispute_id)
            if not dispute:
                return None

            old_status = dispute.status
            dispute.recalculate_status(tenant_complete, landlord_complete)

            if old_status != dispute.status:
                logger.info(
                    "dispute_status_recalculated",
                    dispute_id=dispute_id,
                    old_status=old_status.value,
                    new_status=dispute.status.value,
                    tenant_complete=tenant_complete,
                    landlord_complete=landlord_complete,
                )

            await uow.disputes.save(dispute)

        return dispute

    async def list_disputes(
        self,
        status: Optional[DisputeStatus] = None,
        limit: int = 100,
    ) -> List[DisputeCase]:
        """List disputes with optional filtering."""
        async with UnitOfWork(self._sm) as uow:
            disputes = await uow.disputes.list_all()

        if status:
            disputes = [d for d in disputes if d.status == status]

        # Sort by created_at descending
        disputes.sort(key=lambda d: d.created_at, reverse=True)

        return disputes[:limit]

    async def delete_dispute(self, dispute_id: str) -> bool:
        """Delete a dispute. Returns True if it existed, False otherwise."""
        async with UnitOfWork(self._sm) as uow:
            existing = await uow.disputes.get(dispute_id)
            if existing is None:
                return False
            await uow.disputes.delete(dispute_id)

        logger.info("dispute_deleted", dispute_id=dispute_id)
        return True

    async def save_dispute(self, dispute: DisputeCase) -> None:
        """
        Persist a dispute case directly.

        Public shim used by code that already holds a mutated DisputeCase and
        needs to persist it without going through a higher-level method
        (e.g. legacy router endpoints, MediationService).
        """
        async with UnitOfWork(self._sm) as uow:
            await uow.disputes.save(dispute)

    # ------------------------------------------------------------------
    # Legacy compatibility shims
    # ------------------------------------------------------------------

    def _save_dispute(self, dispute: DisputeCase) -> None:
        """
        Sync shim kept for callers (MediationService) that call this without
        await.  Schedules the async save on the running event loop so it is
        not silently dropped.

        Once MediationService is rewritten (Phase 9.1) this shim can be
        removed.
        """
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.save_dispute(dispute))
        except RuntimeError:
            # No running event loop (e.g. unit-test sync context).  This path
            # is only hit when MediationService tests mock this method anyway,
            # so silently do nothing.
            pass


# ---------------------------------------------------------------------------
# Legacy singleton getter — kept for rollback compatibility.
# The dependencies.py factory no longer calls this; other modules that
# still import it directly will keep working until their own Phase-6.x
# rewrites land.
# ---------------------------------------------------------------------------


def get_dispute_service() -> "DisputeService":
    """Legacy process-singleton getter. Kept for rollback compatibility."""
    global _dispute_service
    if _dispute_service is None:
        # Build a minimal no-op sessionmaker so the singleton can still be
        # constructed (e.g. for tests that patch the service).  Real requests
        # always go through dependencies.get_dispute_service() which injects
        # the app engine's sessionmaker.
        from sqlalchemy.ext.asyncio import create_async_engine
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        from sqlalchemy.ext.asyncio import async_sessionmaker as _asm
        sm = _asm(engine, expire_on_commit=False, class_=AsyncSession)
        _dispute_service = DisputeService(sessionmaker=sm)
    return _dispute_service
