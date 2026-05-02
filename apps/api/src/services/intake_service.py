"""
Intake service.

Orchestrates the intake conversation flow and session management.
Persistence is routed through a UnitOfWork backed by Postgres (Phase 6.1).
"""

from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llm_orchestrator.agents.intake_agent import IntakeAgent
from llm_orchestrator.clients.factory import get_llm_client
from llm_orchestrator.clients.types import LLMRole
from llm_orchestrator.config import LLMConfig
from llm_orchestrator.models.case_file import CaseFile, PartyRole
from llm_orchestrator.models.conversation import ConversationState
from llm_orchestrator.models.dispute import DisputeCase, generate_invite_code

from apps.api.src.db.uow import UnitOfWork
from apps.api.src.db.repositories.sessions_repo import ConcurrentUpdateError
from apps.api.src.domain_runtime import DomainRuntimeContext

logger = structlog.get_logger()

# Global service instance (legacy singleton — kept for rollback compatibility)
_intake_service: Optional["IntakeService"] = None


class IntakeService:
    """
    Service for managing intake conversations.

    Handles session creation, message processing, and persistence.
    All reads/writes go through a UnitOfWork backed by Postgres.
    """

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        *,
        agent: Optional[IntakeAgent] = None,
    ) -> None:
        """
        Initialise the intake service.

        Args:
            sessionmaker: SQLAlchemy async sessionmaker bound to the app engine.
            agent: Optional pre-built IntakeAgent (injected in tests to avoid
                   hitting the LLM).
        """
        logger.debug("initializing_intake_service")
        self._sm = sessionmaker

        if agent is None:
            llm_config = LLMConfig.from_env()
            role_config = llm_config.role_config(LLMRole.INTAKE)
            logger.debug(
                "llm_config_loaded",
                provider=role_config.provider.value,
                primary_model=role_config.primary_model,
                fallback_model=role_config.fallback_model,
            )
            llm_client = get_llm_client(LLMRole.INTAKE, config=llm_config)
            agent = IntakeAgent(llm_client)

        self.agent = agent
        logger.info("intake_service_initialized")

    @staticmethod
    def _stamp_domain_on_dispute(
        dispute: DisputeCase,
        domain_runtime: Optional[DomainRuntimeContext],
    ) -> None:
        """Mirror the domain runtime onto a freshly constructed DisputeCase."""
        if domain_runtime is None:
            return
        spec = domain_runtime.domain_spec
        dispute.domain_id = str(spec.id)
        dispute.domain_version = spec.domain_version
        dispute.matter_types = list(spec.matter_types)
        dispute.routing_metadata = dict(domain_runtime.routing_metadata)

    @staticmethod
    def _stamp_domain(
        conversation: ConversationState,
        domain_runtime: Optional[DomainRuntimeContext],
    ) -> None:
        """Apply the resolved domain runtime onto the ConversationState + CaseFile.

        Phase 3: stamps both the conversation-level and the case-file-level
        domain fields so they round-trip identically. When ``domain_runtime``
        is ``None`` we leave the model defaults in place — that path is the
        existing deposit baseline.
        """
        if domain_runtime is None:
            return
        spec = domain_runtime.domain_spec
        domain_id = str(spec.id)
        version = spec.domain_version
        matter_types = list(spec.matter_types)
        routing_metadata = dict(domain_runtime.routing_metadata)
        conversation.domain_id = domain_id
        conversation.domain_version = version
        conversation.matter_types = matter_types
        conversation.routing_metadata = routing_metadata
        conversation.case_file.domain_id = domain_id
        conversation.case_file.domain_version = version
        conversation.case_file.matter_types = matter_types
        conversation.case_file.routing_metadata = routing_metadata

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_session(
        self,
        role: Optional[str] = None,
        *,
        domain_runtime: Optional[DomainRuntimeContext] = None,
    ) -> tuple[str, str, str]:
        """
        Start a new intake session with optional role.

        If role is provided, the session will start with the role already set
        and the first question will be role-appropriate.

        Args:
            role: Optional user role ("tenant" or "landlord")

        Returns:
            Tuple of (greeting, session_id, stage)
        """
        logger.debug("starting_new_session", role=role)

        user_role = PartyRole(role) if role else None
        logger.debug(
            "party_role_parsed", user_role=user_role.value if user_role else None
        )

        # LLM call — OUTSIDE any transaction
        greeting, conversation = await self.agent.start_conversation(
            user_role=user_role
        )

        # SHA-20 Phase 3: stamp domain routing metadata onto the new
        # conversation before any persistence so the projection columns and
        # the canonical payload agree from the first save.
        self._stamp_domain(conversation, domain_runtime)

        logger.debug(
            "conversation_created",
            session_id=conversation.session_id,
            stage=conversation.current_stage.value,
            role=conversation.case_file.user_role.value
            if conversation.case_file.user_role
            else None,
            greeting_length=len(greeting),
            domain_id=conversation.domain_id,
        )

        # Persist via UoW
        async with UnitOfWork(self._sm) as uow:
            await uow.sessions.save(conversation)

        logger.info(
            "intake_session_started",
            session_id=conversation.session_id,
            role=role,
        )

        return greeting, conversation.session_id, conversation.current_stage.value

    async def start_session_with_dispute(
        self,
        *,
        role: str,
        invite_code: Optional[str] = None,
        create_dispute: bool = False,
        property_address: Optional[str] = None,
        property_postcode: Optional[str] = None,
        deposit_amount: Optional[float] = None,
        domain_runtime: Optional[DomainRuntimeContext] = None,
    ) -> "tuple[str, ConversationState, Optional[DisputeCase]]":
        """Start a session AND create/join its dispute in one transaction.

        Returns (greeting, conversation_state, dispute_or_none).

        Atomic: if the dispute write fails, the session write is rolled back too.
        The LLM call happens BEFORE the transaction; inside the transaction we do
        only DB work.

        When invite_code is provided and the join fails (code not found, or slot
        taken), the session write is still committed and (greeting, state, None)
        is returned — the caller decides how to surface the failure.
        """
        logger.debug(
            "starting_session_with_dispute",
            role=role,
            has_invite_code=bool(invite_code),
            create_dispute=create_dispute,
        )

        user_role = PartyRole(role) if role else None

        # LLM call — OUTSIDE any transaction
        greeting, conversation = await self.agent.start_conversation(user_role=user_role)
        self._stamp_domain(conversation, domain_runtime)
        session_id = conversation.session_id

        if invite_code:
            # ---- join path ------------------------------------------------
            # Attempt to join inside a single UoW so the session save and the
            # dispute update are either both committed or both rolled back.
            normalized = invite_code.upper().strip()
            async with UnitOfWork(self._sm) as uow:
                await uow.sessions.save(conversation)

                dispute = await uow.disputes.lock_by_invite_code(normalized)
                if dispute is None:
                    logger.warning("invite_code_not_found", invite_code=invite_code)
                    # Session committed; dispute not found — return cleanly.
                    return greeting, conversation, None

                if role == "tenant":
                    if dispute.tenant_session_id and dispute.tenant_session_id != session_id:
                        logger.warning(
                            "tenant_slot_taken", dispute_id=dispute.dispute_id
                        )
                        return greeting, conversation, None
                    dispute.link_tenant_session(session_id)
                elif role == "landlord":
                    if dispute.landlord_session_id and dispute.landlord_session_id != session_id:
                        logger.warning(
                            "landlord_slot_taken", dispute_id=dispute.dispute_id
                        )
                        return greeting, conversation, None
                    dispute.link_landlord_session(session_id)

                await uow.disputes.save(dispute)

            logger.info(
                "session_joined_dispute_atomically",
                session_id=session_id,
                dispute_id=dispute.dispute_id,
            )
            return greeting, conversation, dispute

        elif create_dispute:
            # ---- create path ----------------------------------------------
            # Build the dispute *outside* the loop; regenerate only invite_code
            # on each retry (mirrors DisputeService.create_dispute).
            dispute_obj: Optional[DisputeCase] = DisputeCase(
                created_by_role=role,
                property_address=property_address,
                property_postcode=property_postcode,
                deposit_amount=deposit_amount,
            )
            self._stamp_domain_on_dispute(dispute_obj, domain_runtime)
            if role == "tenant":
                dispute_obj.link_tenant_session(session_id)
            else:
                dispute_obj.link_landlord_session(session_id)

            _MAX_RETRIES = 5
            for attempt in range(_MAX_RETRIES):
                dispute_obj.invite_code = generate_invite_code()
                try:
                    async with UnitOfWork(self._sm) as uow:
                        existing = await uow.disputes.get_by_invite_code(dispute_obj.invite_code)
                        if existing is not None:
                            logger.debug(
                                "invite_code_collision_precheck",
                                code=dispute_obj.invite_code,
                                attempt=attempt,
                            )
                            continue

                        await uow.sessions.save(conversation)
                        await uow.disputes.save(dispute_obj)
                    # UoW committed — both rows are durable.
                    break
                except IntegrityError:
                    # Race with another writer; regenerate and retry.
                    logger.debug(
                        "invite_code_integrity_error_retry",
                        code=dispute_obj.invite_code,
                        attempt=attempt,
                    )
                    continue
            else:
                raise RuntimeError(
                    "Could not generate a unique invite code after "
                    f"{_MAX_RETRIES} attempts"
                )

            logger.info(
                "dispute_created_with_session_atomically",
                session_id=session_id,
                dispute_id=dispute_obj.dispute_id,
                invite_code=dispute_obj.invite_code,
            )
            return greeting, conversation, dispute_obj

        else:
            # ---- standalone (no dispute) path ----------------------------
            # This path should not normally be reached via this method — the
            # router should call start_session() instead — but we support it
            # for completeness.
            async with UnitOfWork(self._sm) as uow:
                await uow.sessions.save(conversation)

            logger.info(
                "intake_session_started_no_dispute",
                session_id=session_id,
                role=role,
            )
            return greeting, conversation, None

    async def process_message(
        self,
        session_id: str,
        message: str,
    ) -> Dict[str, Any]:
        """
        Process a message in an intake session.

        Role must be set via set_role() before processing messages.
        If role is not set, conversation will remain at GREETING stage.

        Args:
            session_id: The session ID
            message: User's message

        Returns:
            Dict with response, stage, completeness, case_file
        """
        logger.debug(
            "processing_message", session_id=session_id, message_length=len(message)
        )

        # Read snapshot + version for optimistic locking
        async with UnitOfWork(self._sm) as uow:
            versioned = await uow.sessions.get_with_version(session_id)

        if versioned is None:
            logger.error("session_not_found_for_message", session_id=session_id)
            raise ValueError(f"Session not found: {session_id}")

        logger.debug(
            "session_retrieved",
            session_id=session_id,
            current_stage=versioned.state.current_stage.value,
            message_count=len(versioned.state.messages),
            user_role=versioned.state.case_file.user_role.value
            if versioned.state.case_file.user_role
            else None,
        )

        # LLM call — OUTSIDE any transaction
        logger.debug("calling_agent_process_message", session_id=session_id)
        response, updated_conversation = await self.agent.process_message(
            versioned.state, message
        )

        logger.debug(
            "agent_response_received",
            session_id=session_id,
            response_length=len(response),
            new_stage=updated_conversation.current_stage.value,
            completeness=updated_conversation.case_file.completeness_score,
            is_complete=updated_conversation.is_complete,
        )

        # Update intake_complete flag based on ALL required fields being present
        case_file = updated_conversation.case_file
        case_file.calculate_completeness()
        missing_required = case_file.get_missing_required_info()

        if case_file.has_all_required_info() and not case_file.intake_complete:
            case_file.intake_complete = True
            logger.info(
                "intake_marked_complete_all_required_fields_present",
                session_id=session_id,
                completeness=case_file.completeness_score,
            )

        logger.debug(
            "intake_validation",
            session_id=session_id,
            has_all_required=case_file.has_all_required_info(),
            missing_required=missing_required,
            intake_complete=case_file.intake_complete,
        )

        # Persist with optimistic locking, then sync linked dispute(s)
        async with UnitOfWork(self._sm) as uow:
            try:
                await uow.sessions.save(
                    updated_conversation, expected_version=versioned.version
                )
            except ConcurrentUpdateError:
                logger.warning(
                    "concurrent_update_detected",
                    session_id=session_id,
                    version=versioned.version,
                )
                raise

            # Keep any linked dispute in sync inside the same transaction. If
            # the dispute update fails, the session save rolls back too.
            await self._sync_dispute_from_case_file(
                uow,
                session_id=session_id,
                case_file=case_file,
                role=case_file.user_role.value if case_file.user_role else None,
            )

        return {
            "response": response,
            "stage": updated_conversation.current_stage.value,
            "completeness": updated_conversation.case_file.completeness_score,
            "is_complete": updated_conversation.is_complete,
            "case_file": updated_conversation.case_file.model_dump(mode="json"),
            "suggested_actions": self._get_suggested_actions(updated_conversation),
        }

    async def set_role(
        self,
        session_id: str,
        role: str,
    ) -> Dict[str, Any]:
        """
        Explicitly set the user's role (for button-triggered UI flows).

        Args:
            session_id: The session ID
            role: User role ("tenant" or "landlord")

        Returns:
            Dict with response, stage, completeness, case_file
        """
        logger.debug("setting_role", session_id=session_id, role=role)

        async with UnitOfWork(self._sm) as uow:
            conversation = await uow.sessions.get(session_id)

        if not conversation:
            logger.error("session_not_found_for_role", session_id=session_id)
            raise ValueError(f"Session not found: {session_id}")

        logger.debug(
            "session_retrieved_for_role",
            session_id=session_id,
            current_stage=conversation.current_stage.value,
        )

        user_role = PartyRole(role)
        logger.debug(
            "party_role_created", session_id=session_id, party_role=user_role.value
        )

        # LLM call — OUTSIDE any transaction
        logger.debug("calling_agent_set_user_role", session_id=session_id)
        response, updated_conversation = await self.agent.set_user_role(
            conversation, user_role
        )

        logger.debug(
            "agent_role_response_received",
            session_id=session_id,
            response_length=len(response),
            new_stage=updated_conversation.current_stage.value,
        )

        # Persist
        async with UnitOfWork(self._sm) as uow:
            await uow.sessions.save(updated_conversation)

        logger.info(
            "intake_role_set",
            session_id=session_id,
            role=role,
            stage=updated_conversation.current_stage.value,
        )

        return {
            "response": response,
            "stage": updated_conversation.current_stage.value,
            "completeness": updated_conversation.case_file.completeness_score,
            "is_complete": updated_conversation.is_complete,
            "case_file": updated_conversation.case_file.model_dump(mode="json"),
            "role_set": True,
        }

    async def bulk_intake(
        self,
        role: str,
        case_text: str,
        *,
        domain_runtime: Optional[DomainRuntimeContext] = None,
    ) -> Dict[str, Any]:
        """
        Process a complete case description in one shot.

        Creates a session, extracts all facts from the pasted text,
        and returns the populated case file. The user can then
        continue in the normal chat flow to add more details.
        """
        conversation, extraction_result, summary = await self._prepare_bulk_intake(
            role=role,
            case_text=case_text,
            domain_runtime=domain_runtime,
        )

        # Persist after all LLM work is done
        async with UnitOfWork(self._sm) as uow:
            await uow.sessions.save(conversation)

        logger.info(
            "bulk_intake_complete",
            session_id=conversation.session_id,
            completeness=conversation.case_file.completeness_score,
            missing=conversation.case_file.missing_info,
            intake_complete=conversation.case_file.intake_complete,
        )

        return self._bulk_response(conversation, extraction_result, summary)

    async def bulk_intake_with_dispute(
        self,
        *,
        role: str,
        case_text: str,
        invite_code: Optional[str] = None,
        create_dispute: bool = False,
        domain_runtime: Optional[DomainRuntimeContext] = None,
    ) -> tuple[Dict[str, Any], Optional[DisputeCase]]:
        """Run bulk intake and create/join the linked dispute in one DB transaction."""
        conversation, extraction_result, summary = await self._prepare_bulk_intake(
            role=role,
            case_text=case_text,
            domain_runtime=domain_runtime,
        )
        case_file = conversation.case_file
        session_id = conversation.session_id
        dispute_obj: Optional[DisputeCase] = None

        if invite_code:
            normalized = invite_code.upper().strip()
            async with UnitOfWork(self._sm) as uow:
                await uow.sessions.save(conversation)

                dispute_obj = await uow.disputes.lock_by_invite_code(normalized)
                if dispute_obj is None:
                    logger.warning("bulk_invite_code_not_found", invite_code=invite_code)
                    return self._bulk_response(conversation, extraction_result, summary), None

                if role == "tenant":
                    if (
                        dispute_obj.tenant_session_id
                        and dispute_obj.tenant_session_id != session_id
                    ):
                        logger.warning(
                            "bulk_tenant_slot_taken",
                            dispute_id=dispute_obj.dispute_id,
                        )
                        return self._bulk_response(
                            conversation, extraction_result, summary
                        ), None
                    dispute_obj.link_tenant_session(session_id)
                elif role == "landlord":
                    if (
                        dispute_obj.landlord_session_id
                        and dispute_obj.landlord_session_id != session_id
                    ):
                        logger.warning(
                            "bulk_landlord_slot_taken",
                            dispute_id=dispute_obj.dispute_id,
                        )
                        return self._bulk_response(
                            conversation, extraction_result, summary
                        ), None
                    dispute_obj.link_landlord_session(session_id)

                self._apply_case_file_to_dispute(dispute_obj, case_file, role)
                await uow.disputes.save(dispute_obj)

            return self._bulk_response(conversation, extraction_result, summary), dispute_obj

        if create_dispute:
            dispute_obj = DisputeCase(
                created_by_role=role,
                property_address=case_file.property.address,
                property_postcode=case_file.property.postcode,
                deposit_amount=case_file.tenancy.deposit_amount,
            )
            self._stamp_domain_on_dispute(dispute_obj, domain_runtime)
            if role == "tenant":
                dispute_obj.link_tenant_session(session_id)
            else:
                dispute_obj.link_landlord_session(session_id)
            self._apply_case_file_to_dispute(dispute_obj, case_file, role)

            _MAX_RETRIES = 5
            for attempt in range(_MAX_RETRIES):
                dispute_obj.invite_code = generate_invite_code()
                try:
                    async with UnitOfWork(self._sm) as uow:
                        existing = await uow.disputes.get_by_invite_code(
                            dispute_obj.invite_code
                        )
                        if existing is not None:
                            logger.debug(
                                "bulk_invite_code_collision_precheck",
                                code=dispute_obj.invite_code,
                                attempt=attempt,
                            )
                            continue

                        await uow.sessions.save(conversation)
                        await uow.disputes.save(dispute_obj)
                    break
                except IntegrityError:
                    logger.debug(
                        "bulk_invite_code_integrity_error_retry",
                        code=dispute_obj.invite_code,
                        attempt=attempt,
                    )
                    continue
            else:
                raise RuntimeError(
                    "Could not generate a unique invite code after "
                    f"{_MAX_RETRIES} attempts"
                )

            return self._bulk_response(conversation, extraction_result, summary), dispute_obj

        async with UnitOfWork(self._sm) as uow:
            await uow.sessions.save(conversation)

        return self._bulk_response(conversation, extraction_result, summary), None

    async def get_session_status(self, session_id: str) -> Optional[Dict]:
        """Get the status of a session."""
        async with UnitOfWork(self._sm) as uow:
            conversation = await uow.sessions.get(session_id)

        if not conversation:
            return None

        messages = []
        for msg in conversation.messages:
            messages.append(
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp if hasattr(msg, "timestamp") else None,
                }
            )

        return {
            "session_id": session_id,
            "stage": conversation.current_stage.value,
            "completeness": conversation.case_file.completeness_score,
            "is_complete": conversation.is_complete,
            "message_count": len(conversation.messages),
            "case_file": conversation.case_file.model_dump(mode="json"),
            "messages": messages,
        }

    async def get_case_file(self, case_id: str) -> Optional[CaseFile]:
        """Get a case file by case ID (uses the unique index on case_id)."""
        async with UnitOfWork(self._sm) as uow:
            state = await uow.sessions.get_by_case_id(case_id)
        return state.case_file if state else None

    async def get_session_id_for_case(self, case_id: str) -> Optional[str]:
        """Return the session_id whose case_file.case_id matches case_id."""
        async with UnitOfWork(self._sm) as uow:
            state = await uow.sessions.get_by_case_id(case_id)
        return state.session_id if state else None

    async def get_case_file_by_session(self, session_id: str) -> Optional[CaseFile]:
        """Return the case file for a given session_id."""
        async with UnitOfWork(self._sm) as uow:
            state = await uow.sessions.get(session_id)
        return state.case_file if state else None

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session. Returns True if it existed."""
        async with UnitOfWork(self._sm) as uow:
            existing = await uow.sessions.get(session_id)
            if existing is None:
                return False
            await uow.sessions.delete(session_id)
        return True

    async def delete_case(self, case_id: str) -> bool:
        """Delete a case and its associated session."""
        async with UnitOfWork(self._sm) as uow:
            state = await uow.sessions.get_by_case_id(case_id)
            if state is None:
                return False
            await uow.sessions.delete(state.session_id)
        return True

    async def list_sessions(self) -> List[Dict]:
        """List all sessions."""
        async with UnitOfWork(self._sm) as uow:
            all_states = await uow.sessions.list_all()

        return [
            {
                "session_id": s.session_id,
                "case_id": s.case_file.case_id,
                "stage": s.current_stage.value,
                "is_complete": s.is_complete,
            }
            for s in all_states
        ]

    async def list_cases(self) -> List[Dict]:
        """List all cases."""
        async with UnitOfWork(self._sm) as uow:
            all_states = await uow.sessions.list_all()

        seen: set[str] = set()
        cases: List[Dict] = []
        for s in all_states:
            cf = s.case_file
            if cf.case_id not in seen:
                cases.append(
                    {
                        "case_id": cf.case_id,
                        "user_role": cf.user_role.value,
                        "intake_complete": cf.intake_complete,
                        "completeness_score": cf.completeness_score,
                        "created_at": cf.created_at,
                    }
                )
                seen.add(cf.case_id)

        return cases

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _prepare_bulk_intake(
        self,
        *,
        role: str,
        case_text: str,
        domain_runtime: Optional[DomainRuntimeContext] = None,
    ) -> tuple[ConversationState, Any, str]:
        logger.debug("bulk_intake_start", role=role, text_length=len(case_text))

        user_role = PartyRole(role)

        # LLM calls — OUTSIDE any transaction
        _, conversation = await self.agent.start_conversation(user_role=user_role)
        self._stamp_domain(conversation, domain_runtime)
        conversation.add_user_message(case_text)

        extraction_result = await self.agent.extractor.extract_bulk(
            case_text=case_text,
            case_file=conversation.case_file,
        )

        conversation.case_file = extraction_result.updated_case_file
        conversation.case_file.calculate_completeness()
        conversation.case_file.get_missing_required_info()

        if conversation.case_file.has_all_required_info():
            conversation.case_file.intake_complete = True

        stage = self._determine_bulk_stage(conversation.case_file)
        conversation.advance_stage(stage)

        summary = self._build_extraction_summary(
            extraction_result, conversation.case_file
        )
        conversation.add_assistant_message(summary)
        return conversation, extraction_result, summary

    @staticmethod
    def _bulk_response(
        conversation: ConversationState,
        extraction_result: Any,
        summary: str,
    ) -> Dict[str, Any]:
        return {
            "session_id": conversation.session_id,
            "response": summary,
            "stage": conversation.current_stage.value,
            "completeness": conversation.case_file.completeness_score,
            "is_complete": conversation.is_complete,
            "case_file": conversation.case_file.model_dump(mode="json"),
            "missing_info": conversation.case_file.missing_info,
            "extraction_successful": not extraction_result.no_new_info,
        }

    async def _sync_dispute_from_case_file(
        self,
        uow: UnitOfWork,
        *,
        session_id: str,
        case_file: CaseFile,
        role: Optional[str],
    ) -> None:
        disputes = await uow.disputes.lock_by_session_id(session_id)
        for dispute in disputes:
            self._apply_case_file_to_dispute(dispute, case_file, role)
            await uow.disputes.save(dispute)

    @staticmethod
    def _apply_case_file_to_dispute(
        dispute: DisputeCase,
        case_file: CaseFile,
        role: Optional[str],
    ) -> None:
        if case_file.property.address and not dispute.property_address:
            dispute.property_address = case_file.property.address
        if case_file.property.postcode and not dispute.property_postcode:
            dispute.property_postcode = case_file.property.postcode
        if case_file.tenancy.deposit_amount is not None and dispute.deposit_amount is None:
            dispute.deposit_amount = case_file.tenancy.deposit_amount

        if case_file.intake_complete and role:
            dispute.mark_party_complete(role)
        else:
            dispute.update_timestamp()

    def _determine_bulk_stage(self, case_file):
        from llm_orchestrator.models.conversation import IntakeStage

        if case_file.has_all_required_info():
            return IntakeStage.CONFIRMATION
        if case_file.issues:
            return IntakeStage.EVIDENCE_COLLECTION
        if case_file.tenancy.deposit_amount is not None:
            return IntakeStage.ISSUE_IDENTIFICATION
        if case_file.tenancy.start_date:
            return IntakeStage.DEPOSIT_DETAILS
        if case_file.property.address:
            return IntakeStage.TENANCY_DETAILS
        return IntakeStage.BASIC_DETAILS

    def _build_extraction_summary(self, extraction_result, case_file) -> str:
        parts = ["Here's what I extracted from your description:\n"]

        if case_file.property.address:
            parts.append(f"**Property:** {case_file.property.address}")
        if case_file.tenancy.start_date:
            parts.append(f"**Tenancy Start:** {case_file.tenancy.start_date}")
        if case_file.tenancy.end_date:
            parts.append(f"**Tenancy End:** {case_file.tenancy.end_date}")
        if case_file.tenancy.deposit_amount:
            parts.append(f"**Deposit:** £{case_file.tenancy.deposit_amount}")
        if case_file.tenancy.deposit_protected is not None:
            status = (
                "Protected" if case_file.tenancy.deposit_protected else "Not protected"
            )
            parts.append(f"**Deposit Protection:** {status}")
        if case_file.issues:
            issues_str = ", ".join(
                i.value.replace("_", " ").title() for i in case_file.issues
            )
            parts.append(f"**Issues:** {issues_str}")
        if case_file.evidence:
            ev_str = ", ".join(
                e.type.value.replace("_", " ").title() for e in case_file.evidence
            )
            parts.append(f"**Evidence:** {ev_str}")

        missing = case_file.missing_info
        if missing:
            parts.append(f"\n**Still needed:** {', '.join(missing)}")
            parts.append("You can continue chatting to provide the missing details.")
        else:
            parts.append(
                "\nAll required information has been collected! You can generate a prediction or continue adding details."
            )

        return "\n".join(parts)

    def _get_suggested_actions(self, conversation: ConversationState) -> List[str]:
        """Get suggested actions based on current state."""
        actions = []
        cf = conversation.case_file

        if cf.has_all_required_info():
            quality = cf.get_data_quality_tier()
            if quality == "minimal":
                actions.append(
                    "Generate prediction (limited data — add more for better results)"
                )
            else:
                actions.append("Generate prediction")
            actions.append("Upload additional evidence")

            recommended_missing = cf.get_missing_recommended_info()
            if recommended_missing:
                actions.append(
                    f"Improve accuracy: add {', '.join(recommended_missing)}"
                )
        else:
            missing = cf.get_missing_required_info()
            if missing:
                actions.append(f"Required: {', '.join(missing)}")

        return actions


# ---------------------------------------------------------------------------
# Legacy singleton getter — kept for rollback compatibility.
# The dependencies.py factory no longer calls this; other modules that
# still import it directly (e.g. mediation_service) will keep working until
# their own Phase-6.x rewrites land.
# ---------------------------------------------------------------------------

def get_intake_service() -> "IntakeService":
    """Legacy process-singleton getter. Kept for rollback compatibility."""
    global _intake_service
    if _intake_service is None:
        # Build a minimal no-op sessionmaker so the singleton can still be
        # constructed (e.g. for tests that patch the service).  Real requests
        # always go through dependencies.get_intake_service() which injects
        # the app engine's sessionmaker.
        from sqlalchemy.ext.asyncio import create_async_engine
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        from sqlalchemy.ext.asyncio import async_sessionmaker as _asm
        sm = _asm(engine, expire_on_commit=False, class_=AsyncSession)
        _intake_service = IntakeService(sessionmaker=sm)
    return _intake_service
