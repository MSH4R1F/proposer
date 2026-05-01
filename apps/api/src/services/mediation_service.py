"""
MediationService — persistence via UnitOfWork (Phase 9.1).

Drops the in-memory `_mediations` dict, `fcntl` file lock, and JSON-file
persistence introduced in the original prototype.  All reads/writes now go
through MediationsRepo + DisputesRepo under a UnitOfWork transaction.

The four atomicity hazards are handled as explicit single-UoW transactions:
  1. start_mediation   — create mediation row + update dispute status atomically.
  2. settle            — update mediation + dispute status in one transaction.
  3. accept_offer→settle — accept path inside respond_to_offer reuses settle().
  4. escalate          — update mediation + dispute status in one transaction.

Legacy singleton path (get_mediation_service / MediationService()) is retained
for backward-compatibility with apps/api/tests/test_mediation.py.
"""

from __future__ import annotations

import json
import os
import fcntl
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llm_orchestrator.agent_loop.trace import TraceSummary
from llm_orchestrator.data.tribunal_costs import get_cost_benefit_analysis
from llm_orchestrator.models.mediation import (
    MediationSession,
    MediationStatus,
    MessageType,
    StructuredOffer,
)
from apps.api.src.config import config

logger = structlog.get_logger()

LEGAL_DISCLAIMER = (
    "This is not legal advice. All information is based on analysis of similar "
    "tribunal cases."
)

# ---------------------------------------------------------------------------
# Legacy singleton (kept for rollback compatibility and test_mediation.py)
# ---------------------------------------------------------------------------
_mediation_service: Optional["MediationService"] = None


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class MediationNotFoundError(ValueError):
    """Raised when a mediation session cannot be found for a dispute."""

    def __init__(self, dispute_id: str) -> None:
        super().__init__(f"Mediation session not found for dispute: {dispute_id}")
        self.dispute_id = dispute_id


class DisputeNotFoundError(ValueError):
    """Raised when a dispute row cannot be found."""

    def __init__(self, dispute_id: str) -> None:
        super().__init__(f"Dispute not found: {dispute_id}")
        self.dispute_id = dispute_id


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class MediationService:
    """
    Service for managing AI-powered mediation sessions.

    When constructed with a *sessionmaker* all state is persisted to Postgres
    via UnitOfWork (Phase 9.1 path).  When constructed without arguments the
    service falls back to the legacy in-memory + JSON-file path so that the
    existing test_mediation.py suite continues to pass without modification.
    """

    def __init__(
        self,
        sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None,
        *,
        mediator_agent: Optional[Any] = None,
    ) -> None:
        logger.debug("initializing_mediation_service")
        self._sm = sessionmaker

        if mediator_agent is None:
            from llm_orchestrator.config import LLMConfig
            llm_config = LLMConfig.from_env()
            mediator_agent = self._build_mediator_agent(llm_config.anthropic_api_key)
        self._mediator = mediator_agent

        # Legacy in-memory state (only used when _sm is None)
        self._mediations: Dict[str, MediationSession] = {}
        self.mediations_dir = config.data_dir / "mediations"
        if self._sm is None:
            self.mediations_dir.mkdir(parents=True, exist_ok=True)
            self._load_sessions()

        logger.info(
            "mediation_service_initialized",
            mode="postgres" if self._sm is not None else "legacy",
        )

    # ------------------------------------------------------------------
    # Legacy helpers (only called in the no-sessionmaker path)
    # ------------------------------------------------------------------

    def _load_sessions(self) -> None:
        for path in self.mediations_dir.glob("mediation_*.json"):
            try:
                with open(path) as f:
                    data = json.load(f)
                session = MediationSession.model_validate(data)
                self._mediations[session.dispute_id] = session
                logger.debug("loaded_mediation_session", dispute_id=session.dispute_id)
            except Exception as e:
                logger.error(
                    "failed_to_load_mediation_session", path=str(path), error=str(e)
                )

    def _save_session(self, session: MediationSession) -> None:
        path = self.mediations_dir / f"mediation_{session.dispute_id}.json"
        data = session.model_dump(mode="json")

        with open(path, "a+") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.seek(0)
                f.truncate()
                json.dump(data, f, indent=2, default=str)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        logger.debug(
            "saved_mediation_session", dispute_id=session.dispute_id, path=str(path)
        )

    # ------------------------------------------------------------------
    # Pure / stateless helpers (both paths)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_mediator_agent(api_key: str) -> Any:
        from llm_orchestrator.agents.mediator_agent import MediatorAgent
        from llm_orchestrator.clients.factory import get_llm_client
        from llm_orchestrator.clients.types import LLMProvider, LLMRole
        from llm_orchestrator.config import LLMConfig

        llm_config = LLMConfig.from_env()
        role_config = llm_config.role_config(LLMRole.MEDIATOR)
        if role_config.provider == LLMProvider.ANTHROPIC and not api_key:
            logger.warning("mediator_llm_key_missing_using_deterministic_fallback")
            return MediatorAgent(_DeterministicMediatorLLM())
        return MediatorAgent(
            get_llm_client(LLMRole.MEDIATOR, config=llm_config),
            provider=role_config.provider,
        )

    @staticmethod
    def _enforce_legal_disclaimer(content: str) -> str:
        cleaned = (content or "").strip()
        if not cleaned:
            cleaned = (
                "I can share neutral information based on similar tribunal outcomes to "
                "help both parties evaluate next negotiation steps."
            )
        if LEGAL_DISCLAIMER in cleaned:
            return cleaned
        return f"{cleaned}\n\n{LEGAL_DISCLAIMER}"

    def _add_ai_mediator_message(
        self,
        session: MediationSession,
        content: str,
        message_type: MessageType = MessageType.AI_MEDIATOR,
        metadata: Optional[Dict[str, Any]] = None,
        offer_id: Optional[str] = None,
        reasoning_trace: Optional[TraceSummary] = None,
    ) -> Any:
        msg = session.add_message(
            sender_role="ai_mediator",
            content=self._enforce_legal_disclaimer(content),
            message_type=message_type,
            metadata=metadata,
            offer_id=offer_id,
        )
        if reasoning_trace is not None:
            msg.reasoning_trace = reasoning_trace
        return msg

    @staticmethod
    def _coerce_prediction_outcome(raw_outcome: Any) -> str:
        normalized = str(raw_outcome or "uncertain").strip().lower()
        mapping = {
            "tenant_wins": "tenant_win",
            "tenant_win": "tenant_win",
            "landlord_wins": "landlord_win",
            "landlord_win": "landlord_win",
            "split": "split",
            "uncertain": "uncertain",
        }
        return mapping.get(normalized, "uncertain")

    @staticmethod
    def _coerce_string_list(value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if item is not None]

    @staticmethod
    def _clamp_confidence(value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.5
        return min(max(confidence, 0.0), 1.0)

    def _build_prediction_result(
        self,
        prediction_data: Dict[str, Any],
        dispute_id: str,
    ) -> Any:
        from llm_orchestrator.models.prediction import PredictionResult

        settlement_range = prediction_data.get("predicted_settlement_range")
        normalized_range = None
        if isinstance(settlement_range, (list, tuple)) and len(settlement_range) >= 2:
            try:
                normalized_range = (
                    float(settlement_range[0]),
                    float(settlement_range[1]),
                )
            except (TypeError, ValueError):
                normalized_range = None

        payload = {
            "case_id": str(prediction_data.get("case_id") or f"case-{dispute_id}"),
            "prediction_id": str(
                prediction_data.get("prediction_id") or f"pred-{dispute_id}"
            ),
            "timestamp": prediction_data.get("timestamp"),
            "overall_outcome": self._coerce_prediction_outcome(
                prediction_data.get("overall_outcome")
            ),
            "overall_confidence": self._clamp_confidence(
                prediction_data.get("overall_confidence")
            ),
            "predicted_settlement_range": normalized_range,
            "key_strengths": self._coerce_string_list(
                prediction_data.get("key_strengths")
            ),
            "key_weaknesses": self._coerce_string_list(
                prediction_data.get("key_weaknesses")
            ),
            "retrieved_cases": self._coerce_string_list(
                prediction_data.get("retrieved_cases")
            ),
            "outcome_summary": str(prediction_data.get("outcome_summary") or ""),
        }
        return PredictionResult.model_validate(payload)

    @staticmethod
    def _build_expectation_payload(
        prediction_data: Dict[str, Any], role: str
    ) -> Dict[str, Any]:
        analysis = get_cost_benefit_analysis(role=role, prediction_data=prediction_data)
        analysis_payload = analysis.model_dump(mode="json")
        tribunal_costs = analysis_payload["tribunal_costs"]
        settlement_range = [
            analysis_payload["settlement_range_low"],
            analysis_payload["settlement_range_high"],
        ]
        tribunal_cost_to_party: Any
        if role == "tenant":
            tribunal_cost_to_party = tribunal_costs["tenant_costs"]
        else:
            tribunal_cost_to_party = [
                tribunal_costs["landlord_costs_min"],
                tribunal_costs["landlord_costs_max"],
            ]

        return {
            "party_role": role,
            "prediction_summary": {
                "prediction_id": prediction_data.get("prediction_id"),
                "overall_outcome": MediationService._coerce_prediction_outcome(
                    prediction_data.get("overall_outcome")
                ),
                "overall_confidence": MediationService._clamp_confidence(
                    prediction_data.get("overall_confidence")
                ),
                "suggested_amount": analysis_payload["settlement_amount"],
                "settlement_range": settlement_range,
                "key_strengths": MediationService._coerce_string_list(
                    prediction_data.get("key_strengths")
                ),
                "key_weaknesses": MediationService._coerce_string_list(
                    prediction_data.get("key_weaknesses")
                ),
            },
            "party_framing": analysis_payload["party_framing"],
            "cost_benefit": {
                "settlement_option": {
                    "amount": analysis_payload["settlement_amount"],
                    "description": analysis_payload["settlement_framing"],
                },
                "tribunal_option": {
                    "cost_to_party": tribunal_cost_to_party,
                    "timeline": (
                        f"{tribunal_costs['timeline_months_min']}-"
                        f"{tribunal_costs['timeline_months_max']} months"
                    ),
                    "outcome_uncertainty": analysis_payload["tribunal_framing"],
                },
            },
            "tribunal_costs": tribunal_costs,
            # Kept for legacy callers/tests while the web uses the fields above.
            "analysis": analysis_payload,
            "prediction": {
                "prediction_id": prediction_data.get("prediction_id"),
                "overall_outcome": prediction_data.get("overall_outcome"),
                "overall_confidence": prediction_data.get("overall_confidence"),
                "predicted_settlement_range": prediction_data.get(
                    "predicted_settlement_range"
                ),
            },
            "disclaimer": LEGAL_DISCLAIMER,
        }

    @staticmethod
    def _find_offer(session: MediationSession, offer_id: str) -> StructuredOffer:
        for offer in session.offers:
            if offer.id == offer_id:
                return offer
        raise ValueError(f"Offer not found: {offer_id}")

    # ------------------------------------------------------------------
    # UoW helpers
    # ------------------------------------------------------------------

    def _uow(self):
        """Return a fresh UnitOfWork context manager (Postgres path only)."""
        from apps.api.src.db.uow import UnitOfWork
        return UnitOfWork(self._sm)

    # ------------------------------------------------------------------
    # Public API — Postgres path (sessionmaker provided)
    # ------------------------------------------------------------------

    async def start_mediation(self, dispute_id: str, session_id: str) -> Dict[str, Any]:
        if self._sm is None:
            return await self._legacy_start_mediation(dispute_id, session_id)
        return await self._pg_start_mediation(dispute_id, session_id)

    async def _pg_start_mediation(self, dispute_id: str, session_id: str) -> Dict[str, Any]:
        # ── Phase 1: read txn — fetch dispute + prediction ──────────────────
        async with self._uow() as uow:
            dispute = await uow.disputes.get(dispute_id)
            if dispute is None:
                raise DisputeNotFoundError(dispute_id)

            role = self._resolve_role(dispute, session_id)

            existing = await uow.mediations.get_by_dispute_id(dispute_id)
            if existing is not None:
                return {
                    "mediation_id": existing.mediation_id,
                    "dispute_id": dispute_id,
                    "status": existing.status.value,
                    "messages": [
                        message.model_dump(mode="json")
                        for message in existing.messages
                    ],
                    "offers": [
                        offer.model_dump(mode="json")
                        for offer in existing.offers
                    ],
                    "initial_message": (
                        existing.messages[0].model_dump(mode="json")
                        if existing.messages
                        else {}
                    ),
                }

            # Fetch cached prediction via the dispute's cached_prediction_id row field.
            prediction_data = await self._fetch_prediction_data_uow(uow, dispute_id)

        if prediction_data is None:
            raise ValueError(f"Prediction required before mediation: {dispute_id}")

        # ── Phase 2: LLM call (outside txn) ─────────────────────────────────
        prediction = self._build_prediction_result(prediction_data, dispute_id)
        expectation_data_tenant = self._build_expectation_payload(
            prediction_data=prediction_data, role="tenant"
        )
        expectation_data_landlord = self._build_expectation_payload(
            prediction_data=prediction_data, role="landlord"
        )

        try:
            initial_content = await self._mediator.generate_opening_message(
                prediction=prediction,
                dispute=dispute,
                expectation_data_tenant=expectation_data_tenant,
                expectation_data_landlord=expectation_data_landlord,
            )
        except Exception as e:
            logger.error(
                "mediator_opening_generation_failed",
                dispute_id=dispute_id,
                error=str(e),
            )
            initial_content = (
                "I can facilitate this negotiation by sharing likely tribunal patterns, "
                "highlighting realistic settlement ranges, and helping both parties test "
                "offers against comparable outcomes."
            )

        # ── Phase 3: write txn — create mediation + update dispute ───────────
        async with self._uow() as uow:
            # Serialize start idempotency on the dispute row so two starters cannot
            # both observe "no mediation" and race on the mediation.dispute_id key.
            dispute_locked = await uow.disputes.lock(dispute_id)
            if dispute_locked is None:
                raise DisputeNotFoundError(dispute_id)

            existing = await uow.mediations.get_by_dispute_id(dispute_id)
            if existing is not None:
                return {
                    "mediation_id": existing.mediation_id,
                    "dispute_id": dispute_id,
                    "status": existing.status.value,
                    "messages": [
                        message.model_dump(mode="json")
                        for message in existing.messages
                    ],
                    "offers": [
                        offer.model_dump(mode="json")
                        for offer in existing.offers
                    ],
                    "initial_message": (
                        existing.messages[0].model_dump(mode="json")
                        if existing.messages
                        else {}
                    ),
                }

            new_mediation = MediationSession(
                dispute_id=dispute_id,
                status=MediationStatus.ACTIVE_NEGOTIATION,
            )
            initial_message = self._add_ai_mediator_message(
                session=new_mediation,
                content=initial_content,
                message_type=MessageType.AI_MEDIATOR,
                metadata={"triggered_by": role},
            )
            await uow.mediations.save(new_mediation)

            dispute_locked.start_mediation()
            await uow.disputes.save(dispute_locked)

        logger.info("mediation_started", dispute_id=dispute_id, session_id=session_id)

        return {
            "mediation_id": new_mediation.mediation_id,
            "dispute_id": dispute_id,
            "status": new_mediation.status.value,
            "messages": [
                message.model_dump(mode="json")
                for message in new_mediation.messages
            ],
            "offers": [
                offer.model_dump(mode="json")
                for offer in new_mediation.offers
            ],
            "initial_message": initial_message.model_dump(mode="json"),
        }

    async def get_expectation_data(
        self, dispute_id: str, session_id: str
    ) -> Dict[str, Any]:
        if self._sm is None:
            return await self._legacy_get_expectation_data(dispute_id, session_id)
        return await self._pg_get_expectation_data(dispute_id, session_id)

    async def _pg_get_expectation_data(
        self, dispute_id: str, session_id: str
    ) -> Dict[str, Any]:
        async with self._uow() as uow:
            dispute = await uow.disputes.get(dispute_id)
            if dispute is None:
                raise DisputeNotFoundError(dispute_id)
            role = self._resolve_role(dispute, session_id)
            prediction_data = await self._fetch_prediction_data_uow(uow, dispute_id)

        if not prediction_data:
            raise ValueError(f"Prediction not found for dispute: {dispute_id}")

        return {
            "dispute_id": dispute_id,
            "session_id": session_id,
            **self._build_expectation_payload(prediction_data, role),
        }

    async def add_message(
        self, dispute_id: str, session_id: str, content: str
    ) -> Dict[str, Any]:
        if self._sm is None:
            return await self._legacy_add_message(dispute_id, session_id, content)
        return await self._pg_add_message(dispute_id, session_id, content)

    async def _pg_add_message(
        self, dispute_id: str, session_id: str, content: str
    ) -> Dict[str, Any]:
        # ── Txn 1: load + validate + persist user message ────────────────────
        async with self._uow() as uow:
            versioned = await uow.mediations.lock_by_dispute_id(dispute_id)
            if versioned is None:
                raise MediationNotFoundError(dispute_id)
            mediation = versioned.session
            if mediation.status != MediationStatus.ACTIVE_NEGOTIATION:
                raise ValueError(
                    f"Mediation must be active for this operation. "
                    f"Current status: {mediation.status.value}"
                )

            dispute = await uow.disputes.get(dispute_id)
            if dispute is None:
                raise DisputeNotFoundError(dispute_id)
            role = self._resolve_role(dispute, session_id)

            prediction_data = await self._fetch_prediction_data_uow(uow, dispute_id)
            if not prediction_data:
                raise ValueError(f"Prediction required before mediation: {dispute_id}")

            user_message = mediation.add_message(
                sender_role=role,
                content=content,
                message_type=MessageType.TEXT,
            )
            await uow.mediations.save(
                mediation, expected_version=versioned.version
            )

        # ── LLM call (outside txn) ───────────────────────────────────────────
        prediction = self._build_prediction_result(prediction_data, dispute_id)
        latest_offer = mediation.get_pending_offer()
        if latest_offer is None and mediation.offers:
            latest_offer = mediation.offers[-1]

        try:
            ai_content = await self._mediator.generate_response(
                messages=mediation.messages,
                prediction=prediction,
                dispute=dispute,
                latest_offer=latest_offer,
            )
        except Exception as e:
            logger.error(
                "mediator_followup_generation_failed",
                dispute_id=dispute_id,
                error=str(e),
            )
            ai_content = (
                "Thank you for sharing your position. Based on comparable tribunal "
                "outcomes, it may help to move toward the predicted settlement range and "
                "focus on evidence each side can substantiate."
            )

        # ── Txn 2: persist AI response ───────────────────────────────────────
        async with self._uow() as uow:
            versioned = await uow.mediations.lock_by_dispute_id(dispute_id)
            if versioned is None:
                raise MediationNotFoundError(dispute_id)
            mediation = versioned.session
            ai_response = self._add_ai_mediator_message(
                session=mediation,
                content=ai_content,
                message_type=MessageType.AI_MEDIATOR,
            )
            await uow.mediations.save(
                mediation, expected_version=versioned.version
            )

        return {
            "dispute_id": dispute_id,
            "user_message": user_message.model_dump(mode="json"),
            "ai_response": ai_response.model_dump(mode="json"),
        }

    async def submit_offer(
        self,
        dispute_id: str,
        session_id: str,
        amount: float,
    ) -> StructuredOffer:
        if self._sm is None:
            return await self._legacy_submit_offer(dispute_id, session_id, amount)
        return await self._pg_submit_offer(dispute_id, session_id, amount)

    async def _pg_submit_offer(
        self, dispute_id: str, session_id: str, amount: float
    ) -> StructuredOffer:
        async with self._uow() as uow:
            versioned = await uow.mediations.lock_by_dispute_id(dispute_id)
            if versioned is None:
                raise MediationNotFoundError(dispute_id)
            mediation = versioned.session
            if mediation.status != MediationStatus.ACTIVE_NEGOTIATION:
                raise ValueError(
                    f"Mediation must be active for this operation. "
                    f"Current status: {mediation.status.value}"
                )

            dispute = await uow.disputes.get(dispute_id)
            if dispute is None:
                raise DisputeNotFoundError(dispute_id)
            role = self._resolve_role(dispute, session_id)

            deposit_amount = dispute.deposit_amount
            if deposit_amount is None:
                raise ValueError("Dispute deposit_amount is required for offer handling")
            deposit_amount = float(deposit_amount)

            if amount < 0 or amount > deposit_amount:
                raise ValueError(
                    f"Offer amount must be within 0 and {deposit_amount:.2f}. Got {amount:.2f}"
                )

            offer = mediation.submit_offer(
                proposed_by_role=role,
                amount=amount,
                deposit_amount=deposit_amount,
            )
            await uow.mediations.save(
                mediation, expected_version=versioned.version
            )

        logger.info(
            "offer_submitted",
            dispute_id=dispute_id,
            session_id=session_id,
            offer_id=offer.id,
            amount=amount,
        )
        return offer

    async def respond_to_offer(
        self,
        dispute_id: str,
        session_id: str,
        offer_id: str,
        action: str,
        counter_amount: Optional[float] = None,
    ) -> Dict[str, Any]:
        if self._sm is None:
            return await self._legacy_respond_to_offer(
                dispute_id, session_id, offer_id, action, counter_amount
            )
        return await self._pg_respond_to_offer(
            dispute_id, session_id, offer_id, action, counter_amount
        )

    async def _pg_respond_to_offer(
        self,
        dispute_id: str,
        session_id: str,
        offer_id: str,
        action: str,
        counter_amount: Optional[float] = None,
    ) -> Dict[str, Any]:
        normalized_action = action.lower().strip()

        if normalized_action == "accept":
            # Atomicity hazard #3: accept → settle in one UoW.
            async with self._uow() as uow:
                versioned = await uow.mediations.lock_by_dispute_id(dispute_id)
                if versioned is None:
                    raise MediationNotFoundError(dispute_id)
                mediation = versioned.session
                if mediation.status != MediationStatus.ACTIVE_NEGOTIATION:
                    raise ValueError(
                        f"Mediation must be active for this operation. "
                        f"Current status: {mediation.status.value}"
                    )

                dispute = await uow.disputes.get(dispute_id)
                if dispute is None:
                    raise DisputeNotFoundError(dispute_id)
                responder_role = self._resolve_role(dispute, session_id)

                offer = self._find_offer(mediation, offer_id)
                if responder_role == offer.proposed_by_role:
                    raise ValueError("Offer responder must be the opposite party")

                accepted_offer = mediation.accept_offer(offer_id, responder_role)
                note = self._add_ai_mediator_message(
                    session=mediation,
                    content=(
                        f"Offer {offer_id} accepted at £{accepted_offer.amount:.2f}. "
                        "The mediation record has been marked as settled. This records "
                        "the parties' stated agreement and is legal information, not "
                        "legal advice."
                    ),
                    message_type=MessageType.SYSTEM,
                    offer_id=offer_id,
                )
                await uow.mediations.save(
                    mediation, expected_version=versioned.version
                )

                dispute_locked = await uow.disputes.lock(dispute_id)
                if dispute_locked is None:
                    raise DisputeNotFoundError(dispute_id)
                dispute_locked.settle()
                await uow.disputes.save(dispute_locked)

            return {
                "action": "accept",
                "offer": accepted_offer.model_dump(mode="json"),
                "settlement_amount": accepted_offer.amount,
                "mediation_status": mediation.status.value,
                "messages": [note.model_dump(mode="json")],
            }

        if normalized_action == "reject":
            async with self._uow() as uow:
                versioned = await uow.mediations.lock_by_dispute_id(dispute_id)
                if versioned is None:
                    raise MediationNotFoundError(dispute_id)
                mediation = versioned.session
                if mediation.status != MediationStatus.ACTIVE_NEGOTIATION:
                    raise ValueError(
                        f"Mediation must be active for this operation. "
                        f"Current status: {mediation.status.value}"
                    )

                dispute = await uow.disputes.get(dispute_id)
                if dispute is None:
                    raise DisputeNotFoundError(dispute_id)
                responder_role = self._resolve_role(dispute, session_id)

                offer = self._find_offer(mediation, offer_id)
                if responder_role == offer.proposed_by_role:
                    raise ValueError("Offer responder must be the opposite party")

                rejected_offer = mediation.reject_offer(offer_id, responder_role)
                note = self._add_ai_mediator_message(
                    session=mediation,
                    content=f"Offer {offer_id} rejected. Parties can continue negotiation.",
                    message_type=MessageType.SYSTEM,
                    offer_id=offer_id,
                )
                await uow.mediations.save(
                    mediation, expected_version=versioned.version
                )

            return {
                "action": "reject",
                "offer": rejected_offer.model_dump(mode="json"),
                "system_message": note.model_dump(mode="json"),
                "mediation_status": mediation.status.value,
                "messages": [note.model_dump(mode="json")],
            }

        if normalized_action == "counter":
            if counter_amount is None:
                raise ValueError("counter_amount is required for counter action")

            async with self._uow() as uow:
                versioned = await uow.mediations.lock_by_dispute_id(dispute_id)
                if versioned is None:
                    raise MediationNotFoundError(dispute_id)
                mediation = versioned.session
                if mediation.status != MediationStatus.ACTIVE_NEGOTIATION:
                    raise ValueError(
                        f"Mediation must be active for this operation. "
                        f"Current status: {mediation.status.value}"
                    )

                dispute = await uow.disputes.get(dispute_id)
                if dispute is None:
                    raise DisputeNotFoundError(dispute_id)
                responder_role = self._resolve_role(dispute, session_id)

                offer = self._find_offer(mediation, offer_id)
                if responder_role == offer.proposed_by_role:
                    raise ValueError("Offer responder must be the opposite party")

                deposit_amount = dispute.deposit_amount
                if deposit_amount is None:
                    raise ValueError("Dispute deposit_amount is required for offer handling")
                deposit_amount = float(deposit_amount)

                if counter_amount < 0 or counter_amount > deposit_amount:
                    raise ValueError(
                        f"Counter amount must be within 0 and {deposit_amount:.2f}. "
                        f"Got {counter_amount:.2f}"
                    )

                counter_offer = mediation.counter_offer(
                    offer_id=offer_id,
                    responder_role=responder_role,
                    counter_amount=counter_amount,
                )
                countered_offer = self._find_offer(mediation, offer_id)
                counter_message = mediation.messages[-1]
                await uow.mediations.save(
                    mediation, expected_version=versioned.version
                )

            return {
                "action": "counter",
                "offer": countered_offer.model_dump(mode="json"),
                "new_offer": counter_offer.model_dump(mode="json"),
                "counter_amount": counter_amount,
                "mediation_status": mediation.status.value,
                "messages": [counter_message.model_dump(mode="json")],
            }

        raise ValueError("action must be one of: accept, reject, counter")

    async def get_messages(
        self,
        dispute_id: str,
        since_timestamp: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if self._sm is None:
            return await self._legacy_get_messages(dispute_id, since_timestamp)
        return await self._pg_get_messages(dispute_id, since_timestamp)

    async def _pg_get_messages(
        self, dispute_id: str, since_timestamp: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        async with self._uow() as uow:
            mediation = await uow.mediations.get_by_dispute_id(dispute_id)
        if mediation is None:
            return []
        messages = mediation.messages
        if since_timestamp:
            messages = [m for m in messages if m.timestamp > since_timestamp]
        return [message.model_dump(mode="json") for message in messages]

    async def get_session(self, dispute_id: str) -> Dict[str, Any]:
        if self._sm is None:
            return await self._legacy_get_session(dispute_id)
        return await self._pg_get_session(dispute_id)

    async def _pg_get_session(self, dispute_id: str) -> Dict[str, Any]:
        async with self._uow() as uow:
            mediation = await uow.mediations.get_by_dispute_id(dispute_id)
        if mediation is None:
            raise MediationNotFoundError(dispute_id)
        return mediation.model_dump(mode="json")

    async def settle(self, dispute_id: str, amount: float) -> Dict[str, Any]:
        if self._sm is None:
            return await self._legacy_settle(dispute_id, amount)
        return await self._pg_settle(dispute_id, amount)

    async def _pg_settle(self, dispute_id: str, amount: float) -> Dict[str, Any]:
        """Atomicity hazard #2 — mediation + dispute status in one UoW."""
        async with self._uow() as uow:
            versioned = await uow.mediations.lock_by_dispute_id(dispute_id)
            if versioned is None:
                raise MediationNotFoundError(dispute_id)
            mediation = versioned.session

            dispute = await uow.disputes.lock(dispute_id)
            if dispute is None:
                raise DisputeNotFoundError(dispute_id)

            deposit_amount = dispute.deposit_amount
            if deposit_amount is not None and (amount < 0 or amount > deposit_amount):
                raise ValueError(
                    f"Settlement amount must be within 0 and {deposit_amount:.2f}. Got {amount:.2f}"
                )

            mediation.settle(amount)
            await uow.mediations.save(
                mediation, expected_version=versioned.version
            )

            dispute.settle()
            await uow.disputes.save(dispute)

        logger.info("mediation_settled", dispute_id=dispute_id, amount=amount)
        return {
            "dispute_id": dispute_id,
            "status": mediation.status.value,
            "settlement_amount": mediation.settlement_amount,
            "settled_at": mediation.settled_at,
        }

    async def escalate(self, dispute_id: str) -> Dict[str, Any]:
        if self._sm is None:
            return await self._legacy_escalate(dispute_id)
        return await self._pg_escalate(dispute_id)

    async def _pg_escalate(self, dispute_id: str) -> Dict[str, Any]:
        """Atomicity hazard #4 — mediation + dispute status in one UoW."""
        async with self._uow() as uow:
            versioned = await uow.mediations.lock_by_dispute_id(dispute_id)
            if versioned is None:
                raise MediationNotFoundError(dispute_id)
            mediation = versioned.session

            dispute = await uow.disputes.lock(dispute_id)
            if dispute is None:
                raise DisputeNotFoundError(dispute_id)

            mediation.escalate()
            note = self._add_ai_mediator_message(
                session=mediation,
                content=(
                    "Mediation has been marked as escalated. The next screen "
                    "summarises formal resolution options as legal information, "
                    "not legal advice."
                ),
                message_type=MessageType.SYSTEM,
            )
            await uow.mediations.save(
                mediation, expected_version=versioned.version
            )

            dispute.escalate()
            await uow.disputes.save(dispute)

        logger.info("mediation_escalated", dispute_id=dispute_id)
        return {
            "dispute_id": dispute_id,
            "mediation_status": mediation.status.value,
            "dispute_status": dispute.status.value,
            "escalated_at": mediation.escalated_at,
            "messages": [note.model_dump(mode="json")],
        }

    async def get_settlement(self, dispute_id: str) -> Dict[str, Any]:
        if self._sm is None:
            return await self._legacy_get_settlement(dispute_id)
        return await self._pg_get_settlement(dispute_id)

    async def _pg_get_settlement(self, dispute_id: str) -> Dict[str, Any]:
        async with self._uow() as uow:
            mediation = await uow.mediations.get_by_dispute_id(dispute_id)
            dispute = await uow.disputes.get(dispute_id)

        if mediation is None:
            raise ValueError(f"Mediation session not found for dispute: {dispute_id}")
        if mediation.status != MediationStatus.SETTLED:
            raise ValueError(f"Mediation not settled for dispute: {dispute_id}")

        return {
            "dispute_id": dispute_id,
            "mediation_id": mediation.mediation_id,
            "status": mediation.status.value,
            "settlement_amount": mediation.settlement_amount,
            "agreed_amount": mediation.settlement_amount,
            "settled_at": mediation.settled_at,
            "started_at": mediation.started_at,
            "updated_at": mediation.updated_at,
            "message_count": len(mediation.messages),
            "offer_count": len(mediation.offers),
            "parties": {
                "tenant_session_id": (
                    getattr(dispute, "tenant_session_id", None) if dispute else None
                ),
                "landlord_session_id": (
                    getattr(dispute, "landlord_session_id", None) if dispute else None
                ),
            },
            "property": {
                "address": getattr(dispute, "property_address", None)
                if dispute
                else None,
                "postcode": getattr(dispute, "property_postcode", None)
                if dispute
                else None,
            },
            "deposit_amount": getattr(dispute, "deposit_amount", None)
            if dispute
            else None,
            "disclaimer": (
                "This settlement summary records information provided through "
                "the mediation flow. It is not legal advice or a legally binding "
                "contract by itself."
            ),
        }

    async def generate_settlement_pdf(self, dispute_id: str) -> bytes:
        if self._sm is None:
            return await self._legacy_generate_settlement_pdf(dispute_id)
        return await self._pg_generate_settlement_pdf(dispute_id)

    async def _pg_generate_settlement_pdf(self, dispute_id: str) -> bytes:
        async with self._uow() as uow:
            mediation = await uow.mediations.get_by_dispute_id(dispute_id)

        if mediation is None:
            raise ValueError(f"Mediation session not found for dispute: {dispute_id}")

        from apps.api.src.utils.pdf_generator import generate_settlement_pdf as _gen_pdf

        settlement_data = await self._pg_get_settlement(dispute_id)
        return _gen_pdf(settlement_data)

    # ------------------------------------------------------------------
    # Internal UoW read helper
    # ------------------------------------------------------------------

    async def _fetch_prediction_data_uow(
        self, uow: Any, dispute_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Try to resolve prediction data via the DB row's cached_prediction_id.

        The cached_prediction_id is stored on DisputeRow (not on DisputeCase's
        Pydantic model payload) so we go via disputes_repo.lock_for_prediction_cache.
        Falls back to legacy service lookup if no cached prediction exists.
        """
        locked = await uow.disputes.lock_for_prediction_cache(dispute_id)
        if locked is None:
            return None
        if locked.cached_prediction_id:
            prediction = await uow.predictions.get(locked.cached_prediction_id)
            if prediction is not None:
                return prediction.model_dump(mode="json")
        # Fall back to legacy prediction service lookup (mirrors original behaviour)
        return await self._get_prediction_data(dispute_id)

    @staticmethod
    def _resolve_role(dispute: Any, session_id: str) -> str:
        """Resolve party role from session_id without a DB call."""
        if dispute.tenant_session_id == session_id:
            return "tenant"
        if dispute.landlord_session_id == session_id:
            return "landlord"
        raise ValueError(
            f"Session {session_id} is not linked to dispute {dispute.dispute_id}"
        )

    # ------------------------------------------------------------------
    # Legacy private methods (kept for the legacy test_mediation.py path)
    # ------------------------------------------------------------------

    async def _legacy_start_mediation(
        self, dispute_id: str, session_id: str
    ) -> Dict[str, Any]:
        from apps.api.src.services.dispute_service import get_dispute_service

        dispute_service = get_dispute_service()
        dispute = await dispute_service.get_dispute(dispute_id)
        if not dispute:
            raise ValueError(f"Dispute not found: {dispute_id}")

        role = await self._get_party_role(dispute_id, session_id)
        prediction_data = await self._get_prediction_data(dispute_id)
        if not prediction_data:
            raise ValueError(f"Prediction required before mediation: {dispute_id}")

        session = self._mediations.get(dispute_id)
        is_new_session = session is None
        if not session:
            session = MediationSession(
                dispute_id=dispute_id, status=MediationStatus.ACTIVE_NEGOTIATION
            )
            self._mediations[dispute_id] = session
        elif session.status == MediationStatus.EXPECTATION_ADJUSTMENT:
            session.status = MediationStatus.ACTIVE_NEGOTIATION
            session.update_timestamp()

        dispute.start_mediation()
        dispute_service._save_dispute(dispute)

        # Only generate an opening message for brand-new sessions to avoid
        # duplicate messages when a party re-opens the chat page.
        initial_message = None
        if is_new_session or not session.messages:
            # Add tenant's position as the first message so the conversation
            # starts from their perspective before the mediator responds.
            from apps.api.src.services.intake_service import get_intake_service
            intake_service = get_intake_service()
            if dispute.tenant_session_id:
                tenant_case_file = await intake_service.get_case_file_by_session(
                    dispute.tenant_session_id
                )
                if tenant_case_file:
                    issues_raw = getattr(tenant_case_file, "issues", None) or []
                    issues = [
                        i.issue_type if hasattr(i, "issue_type") else str(i)
                        for i in issues_raw
                    ]
                    tenancy = getattr(tenant_case_file, "tenancy", None)
                    deposit_amount = getattr(tenancy, "deposit_amount", None) if tenancy else None
                    deposit = f"£{deposit_amount:.0f}" if deposit_amount else "my deposit"
                    property_obj = getattr(tenant_case_file, "property", None)
                    address_value = (
                        getattr(property_obj, "address", None) if property_obj else None
                    )
                    address = address_value or "the property"
                    issues_str = (
                        ", ".join(issues) if issues else "deductions from my deposit"
                    )
                    tenant_opening = (
                        f"I want to resolve a dispute over {deposit} for {address}. "
                        f"The main issues are {issues_str}."
                    )
                    session.add_message(
                        sender_role="tenant",
                        content=tenant_opening,
                        message_type=MessageType.TEXT,
                        metadata={"source": "intake_summary"},
                    )

        if is_new_session or not session.messages or len(session.messages) <= 1:
            prediction = self._build_prediction_result(prediction_data, dispute_id)
            expectation_data_tenant = self._build_expectation_payload(
                prediction_data=prediction_data,
                role="tenant",
            )
            expectation_data_landlord = self._build_expectation_payload(
                prediction_data=prediction_data,
                role="landlord",
            )

            # AgentLoop re-raises on MODEL_ERROR; on MAX_TURNS it returns ("", trace).
            # Either way, the fallback below keeps the mediation session valid.
            trace_summary: Optional[TraceSummary] = None
            try:
                initial_content, trace_summary = await self._mediator.generate_opening_message(
                    prediction=prediction,
                    dispute=dispute,
                    expectation_data_tenant=expectation_data_tenant,
                    expectation_data_landlord=expectation_data_landlord,
                )
                if not initial_content:
                    raise RuntimeError("Mediator returned empty opening (likely MAX_TURNS)")
            except Exception as e:
                logger.error(
                    "mediator_opening_generation_failed",
                    dispute_id=dispute_id,
                    error=str(e),
                )
                initial_content = (
                    "I can facilitate this negotiation by sharing likely tribunal patterns, "
                    "highlighting realistic settlement ranges, and helping both parties test "
                    "offers against comparable outcomes."
                )

            initial_message = self._add_ai_mediator_message(
                session=session,
                content=initial_content,
                message_type=MessageType.AI_MEDIATOR,
                metadata={"triggered_by": role},
                reasoning_trace=trace_summary,
            )

        self._save_session(session)

        logger.info("mediation_started", dispute_id=dispute_id, session_id=session_id)

        return {
            "mediation_id": session.mediation_id,
            "dispute_id": dispute_id,
            "status": session.status.value,
            "initial_message": initial_message.model_dump(mode="json") if initial_message else None,
        }

    async def _legacy_get_expectation_data(
        self, dispute_id: str, session_id: str
    ) -> Dict[str, Any]:
        role = await self._get_party_role(dispute_id, session_id)
        prediction_data = await self._get_prediction_data(dispute_id)
        if not prediction_data:
            raise ValueError(f"Prediction not found for dispute: {dispute_id}")

        return {
            "dispute_id": dispute_id,
            "session_id": session_id,
            **self._build_expectation_payload(prediction_data, role),
        }

    async def _legacy_add_message(
        self, dispute_id: str, session_id: str, content: str
    ) -> Dict[str, Any]:
        from apps.api.src.services.dispute_service import get_dispute_service

        session = await self._require_active_session(dispute_id)
        role = await self._get_party_role(dispute_id, session_id)
        prediction_data = await self._get_prediction_data(dispute_id)
        if not prediction_data:
            raise ValueError(f"Prediction required before mediation: {dispute_id}")

        dispute_service = get_dispute_service()
        dispute = await dispute_service.get_dispute(dispute_id)
        if not dispute:
            raise ValueError(f"Dispute not found: {dispute_id}")

        user_message = session.add_message(
            sender_role=role,
            content=content,
            message_type=MessageType.TEXT,
        )

        prediction = self._build_prediction_result(prediction_data, dispute_id)
        latest_offer = session.get_pending_offer()
        if latest_offer is None and session.offers:
            latest_offer = session.offers[-1]

        # AgentLoop re-raises on MODEL_ERROR; on MAX_TURNS it returns ("", trace).
        # Either way, the fallback message below keeps the mediation session valid.
        trace_summary: Optional[TraceSummary] = None
        try:
            ai_content, trace_summary = await self._mediator.generate_response(
                messages=session.messages,
                prediction=prediction,
                dispute=dispute,
                latest_offer=latest_offer,
            )
        except Exception as e:
            logger.error(
                "mediator_followup_generation_failed",
                dispute_id=dispute_id,
                error=str(e),
            )
            ai_content = (
                "Thank you for sharing your position. Based on comparable tribunal "
                "outcomes, it may help to move toward the predicted settlement range and "
                "focus on evidence each side can substantiate."
            )

        ai_response = self._add_ai_mediator_message(
            session=session,
            content=ai_content,
            message_type=MessageType.AI_MEDIATOR,
            reasoning_trace=trace_summary,
        )

        self._save_session(session)

        return {
            "dispute_id": dispute_id,
            "user_message": user_message.model_dump(mode="json"),
            "ai_response": ai_response.model_dump(mode="json"),
        }

    async def _legacy_submit_offer(
        self,
        dispute_id: str,
        session_id: str,
        amount: float,
    ) -> StructuredOffer:
        session = await self._require_active_session(dispute_id)
        role = await self._get_party_role(dispute_id, session_id)
        deposit_amount = await self._get_deposit_amount(dispute_id)

        if amount < 0 or amount > deposit_amount:
            raise ValueError(
                f"Offer amount must be within 0 and {deposit_amount:.2f}. Got {amount:.2f}"
            )

        offer = session.submit_offer(
            proposed_by_role=role,
            amount=amount,
            deposit_amount=deposit_amount,
        )
        self._save_session(session)

        logger.info(
            "offer_submitted",
            dispute_id=dispute_id,
            session_id=session_id,
            offer_id=offer.id,
            amount=amount,
        )
        return offer

    async def _legacy_respond_to_offer(
        self,
        dispute_id: str,
        session_id: str,
        offer_id: str,
        action: str,
        counter_amount: Optional[float] = None,
    ) -> Dict[str, Any]:
        session = await self._require_active_session(dispute_id)
        responder_role = await self._get_party_role(dispute_id, session_id)
        offer = self._find_offer(session, offer_id)

        if responder_role == offer.proposed_by_role:
            raise ValueError("Offer responder must be the opposite party")

        normalized_action = action.lower().strip()

        if normalized_action == "accept":
            accepted_offer = session.accept_offer(offer_id, responder_role)
            self._save_session(session)
            await self.settle(dispute_id, accepted_offer.amount)
            return {
                "action": "accept",
                "offer": accepted_offer.model_dump(mode="json"),
                "settlement_amount": accepted_offer.amount,
            }

        if normalized_action == "reject":
            rejected_offer = session.reject_offer(offer_id, responder_role)
            note = self._add_ai_mediator_message(
                session=session,
                content=f"Offer {offer_id} rejected. Parties can continue negotiation.",
                message_type=MessageType.SYSTEM,
                offer_id=offer_id,
            )
            self._save_session(session)
            return {
                "action": "reject",
                "offer": rejected_offer.model_dump(mode="json"),
                "system_message": note.model_dump(mode="json"),
            }

        if normalized_action == "counter":
            if counter_amount is None:
                raise ValueError("counter_amount is required for counter action")

            deposit_amount = await self._get_deposit_amount(dispute_id)
            if counter_amount < 0 or counter_amount > deposit_amount:
                raise ValueError(
                    f"Counter amount must be within 0 and {deposit_amount:.2f}. "
                    f"Got {counter_amount:.2f}"
                )

            counter_offer = session.counter_offer(
                offer_id=offer_id,
                responder_role=responder_role,
                counter_amount=counter_amount,
            )
            self._save_session(session)
            return {
                "action": "counter",
                "offer": counter_offer.model_dump(mode="json"),
                "counter_amount": counter_amount,
            }

        raise ValueError("action must be one of: accept, reject, counter")

    async def _legacy_get_messages(
        self, dispute_id: str, since_timestamp: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        session = self._mediations.get(dispute_id)
        if not session:
            return []
        messages = session.messages
        if since_timestamp:
            messages = [m for m in messages if m.timestamp > since_timestamp]
        return [message.model_dump(mode="json") for message in messages]

    async def _legacy_get_session(self, dispute_id: str) -> Dict[str, Any]:
        session = self._mediations.get(dispute_id)
        if not session:
            raise ValueError(f"Mediation session not found for dispute: {dispute_id}")
        return session.model_dump(mode="json")

    async def _legacy_settle(self, dispute_id: str, amount: float) -> Dict[str, Any]:
        from apps.api.src.services.dispute_service import get_dispute_service

        session = self._mediations.get(dispute_id)
        if not session:
            raise ValueError(f"Mediation session not found for dispute: {dispute_id}")

        dispute_service = get_dispute_service()
        dispute = await dispute_service.get_dispute(dispute_id)
        if not dispute:
            raise ValueError(f"Dispute not found: {dispute_id}")

        deposit_amount = dispute.deposit_amount
        if deposit_amount is not None and (amount < 0 or amount > deposit_amount):
            raise ValueError(
                f"Settlement amount must be within 0 and {deposit_amount:.2f}. Got {amount:.2f}"
            )

        session.settle(amount)
        dispute.settle()

        self._save_session(session)
        dispute_service._save_dispute(dispute)

        logger.info("mediation_settled", dispute_id=dispute_id, amount=amount)
        return {
            "dispute_id": dispute_id,
            "status": session.status.value,
            "settlement_amount": session.settlement_amount,
            "settled_at": session.settled_at,
        }

    async def _legacy_escalate(self, dispute_id: str) -> Dict[str, Any]:
        from apps.api.src.services.dispute_service import get_dispute_service

        session = self._mediations.get(dispute_id)
        if not session:
            raise ValueError(f"Mediation session not found for dispute: {dispute_id}")

        dispute_service = get_dispute_service()
        dispute = await dispute_service.get_dispute(dispute_id)
        if not dispute:
            raise ValueError(f"Dispute not found: {dispute_id}")

        session.escalate()
        dispute.escalate()

        self._save_session(session)
        dispute_service._save_dispute(dispute)

        logger.info("mediation_escalated", dispute_id=dispute_id)
        return {
            "dispute_id": dispute_id,
            "mediation_status": session.status.value,
            "dispute_status": dispute.status.value,
            "escalated_at": session.escalated_at,
        }

    async def _legacy_get_settlement(self, dispute_id: str) -> Dict[str, Any]:
        session = self._mediations.get(dispute_id)
        if not session:
            raise ValueError(f"Mediation session not found for dispute: {dispute_id}")
        if session.status != MediationStatus.SETTLED:
            raise ValueError(f"Mediation not settled for dispute: {dispute_id}")
        try:
            from apps.api.src.services.dispute_service import get_dispute_service

            dispute_service = get_dispute_service()
            dispute = await dispute_service.get_dispute(dispute_id)
        except Exception:
            dispute = None
        return {
            "dispute_id": dispute_id,
            "mediation_id": session.mediation_id,
            "status": session.status.value,
            "settlement_amount": session.settlement_amount,
            "agreed_amount": session.settlement_amount,
            "settled_at": session.settled_at,
            "started_at": session.started_at,
            "updated_at": session.updated_at,
            "message_count": len(session.messages),
            "offer_count": len(session.offers),
            "parties": {
                "tenant_session_id": (
                    getattr(dispute, "tenant_session_id", None) if dispute else None
                ),
                "landlord_session_id": (
                    getattr(dispute, "landlord_session_id", None) if dispute else None
                ),
            },
            "property": {
                "address": getattr(dispute, "property_address", None)
                if dispute
                else None,
                "postcode": getattr(dispute, "property_postcode", None)
                if dispute
                else None,
            },
            "deposit_amount": getattr(dispute, "deposit_amount", None)
            if dispute
            else None,
            "disclaimer": (
                "This settlement summary records information provided through "
                "the mediation flow. It is not legal advice or a legally binding "
                "contract by itself."
            ),
        }

    async def _legacy_generate_settlement_pdf(self, dispute_id: str) -> bytes:
        if dispute_id not in self._mediations:
            raise ValueError(f"Mediation session not found for dispute: {dispute_id}")
        from apps.api.src.utils.pdf_generator import generate_settlement_pdf as _gen_pdf
        settlement_data = await self._legacy_get_settlement(dispute_id)
        return _gen_pdf(settlement_data)

    # ------------------------------------------------------------------
    # Legacy helper methods (keep for legacy path)
    # ------------------------------------------------------------------

    async def _get_party_role(self, dispute_id: str, session_id: str) -> str:
        from apps.api.src.services.dispute_service import get_dispute_service

        dispute_service = get_dispute_service()
        dispute = await dispute_service.get_dispute(dispute_id)
        if not dispute:
            raise ValueError(f"Dispute not found: {dispute_id}")

        if dispute.tenant_session_id == session_id:
            return "tenant"
        if dispute.landlord_session_id == session_id:
            return "landlord"
        raise ValueError(f"Session {session_id} is not linked to dispute {dispute_id}")

    async def _require_active_session(self, dispute_id: str) -> MediationSession:
        session = self._mediations.get(dispute_id)
        if not session:
            raise ValueError(f"Mediation session not found for dispute: {dispute_id}")
        if session.status != MediationStatus.ACTIVE_NEGOTIATION:
            raise ValueError(
                f"Mediation must be active for this operation. Current status: {session.status.value}"
            )
        return session

    async def _get_deposit_amount(self, dispute_id: str) -> float:
        from apps.api.src.services.dispute_service import get_dispute_service

        dispute_service = get_dispute_service()
        dispute = await dispute_service.get_dispute(dispute_id)
        if not dispute:
            raise ValueError(f"Dispute not found: {dispute_id}")
        if dispute.deposit_amount is None:
            raise ValueError("Dispute deposit_amount is required for offer handling")
        return float(dispute.deposit_amount)

    async def _get_prediction_data(self, dispute_id: str) -> Optional[Dict[str, Any]]:
        from apps.api.src.services.dispute_service import get_dispute_service
        from apps.api.src.services.intake_service import get_intake_service
        from apps.api.src.services.prediction_service import get_prediction_service

        dispute_service = get_dispute_service()
        intake_service = get_intake_service()
        prediction_service = get_prediction_service()

        dispute = await dispute_service.get_dispute(dispute_id)
        if not dispute:
            raise ValueError(f"Dispute not found: {dispute_id}")

        case_ids: List[str] = []
        if dispute.tenant_session_id:
            tenant_case_file = await intake_service.get_case_file_by_session(
                dispute.tenant_session_id
            )
            if tenant_case_file:
                case_ids.append(tenant_case_file.case_id)
        if dispute.landlord_session_id:
            landlord_case_file = await intake_service.get_case_file_by_session(
                dispute.landlord_session_id
            )
            if landlord_case_file:
                case_ids.append(landlord_case_file.case_id)

        if not case_ids:
            return None

        candidates: List[Dict[str, Any]] = []
        seen_prediction_ids = set()
        for case_id in case_ids:
            summaries = await prediction_service.list_predictions_for_case(case_id)
            for summary in summaries:
                prediction_id = summary.get("prediction_id")
                if not prediction_id or prediction_id in seen_prediction_ids:
                    continue
                seen_prediction_ids.add(prediction_id)
                prediction = await prediction_service.get_prediction(prediction_id)
                if prediction:
                    candidates.append(prediction)

        if not candidates:
            return None

        candidates.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
        return candidates[0]


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------

def get_mediation_service() -> MediationService:
    """Legacy singleton factory — kept for rollback compatibility."""
    global _mediation_service
    if _mediation_service is None:
        _mediation_service = MediationService()
    return _mediation_service


# ---------------------------------------------------------------------------
# Deterministic fallback LLM (used when no API key is available)
# ---------------------------------------------------------------------------

class _DeterministicMediatorLLM:
    """AgentTurnClient stand-in used when ANTHROPIC_API_KEY is missing.

    Returns a single text block per turn with stop_reason="end_turn" — the
    fallback never exercises the tool-calling path, which is the right
    behaviour for an offline local-dev mode (no numbers = no fake numbers).
    """

    async def run_agent_turn(
        self,
        *,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tool_schemas: List[Dict[str, Any]],
        model: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> Any:
        from llm_orchestrator.agent_loop.loop import AgentTurnResponse

        _ = (system_prompt, tool_schemas, model, max_tokens)
        prompt = ""
        if messages:
            last = messages[-1]
            content = last.get("content") if isinstance(last, dict) else ""
            if isinstance(content, str):
                prompt = content.lower()

        if "new mediation session is starting" in prompt:
            text = (
                "This is not legal advice. All information is based on analysis of similar "
                "tribunal cases. Welcome to mediation — I will share neutral information from "
                "comparable outcomes, summarise both perspectives, and help identify a "
                "practical negotiation range."
            )
        else:
            text = (
                "I have noted both positions. Based on comparable tribunal outcomes, it may "
                "be useful to test the latest offer against the likely settlement range and "
                "focus on evidence each side can verify."
            )

        return AgentTurnResponse(
            content_blocks=[{"type": "text", "text": text}],
            stop_reason="end_turn",
            tokens_in=0,
            tokens_out=0,
            model_used="deterministic-fallback",
        )
