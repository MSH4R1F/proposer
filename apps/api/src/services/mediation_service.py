import fcntl
import json
import os
from typing import Any, Dict, List, Optional

import structlog

from llm_orchestrator.data.tribunal_costs import get_cost_benefit_analysis
from llm_orchestrator.models.mediation import (
    MediationSession,
    MediationStatus,
    MessageType,
    StructuredOffer,
)
from apps.api.src.config import config

logger = structlog.get_logger()

_mediation_service: Optional["MediationService"] = None


class MediationService:
    def __init__(self):
        logger.debug("initializing_mediation_service")
        self._mediations: Dict[str, MediationSession] = {}
        self.mediations_dir = config.data_dir / "mediations"
        self.mediations_dir.mkdir(parents=True, exist_ok=True)
        self._load_sessions()

        logger.info(
            "mediation_service_initialized", mediation_count=len(self._mediations)
        )

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

    async def start_mediation(self, dispute_id: str, session_id: str) -> Dict[str, Any]:
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

        initial_content = (
            "I am your AI mediator. Share your priorities and opening position so we can "
            "work toward a fair settlement informed by similar tribunal outcomes."
        )
        initial_message = session.add_message(
            sender_role="ai_mediator",
            content=initial_content,
            message_type=MessageType.AI_MEDIATOR,
            metadata={"triggered_by": role},
        )

        self._save_session(session)

        logger.info("mediation_started", dispute_id=dispute_id, session_id=session_id)

        return {
            "mediation_id": session.mediation_id,
            "dispute_id": dispute_id,
            "status": session.status.value,
            "initial_message": initial_message.model_dump(mode="json"),
        }

    async def get_expectation_data(
        self, dispute_id: str, session_id: str
    ) -> Dict[str, Any]:
        role = await self._get_party_role(dispute_id, session_id)
        prediction_data = await self._get_prediction_data(dispute_id)
        if not prediction_data:
            raise ValueError(f"Prediction not found for dispute: {dispute_id}")

        analysis = get_cost_benefit_analysis(role=role, prediction_data=prediction_data)

        return {
            "dispute_id": dispute_id,
            "session_id": session_id,
            "party_role": role,
            "prediction": {
                "prediction_id": prediction_data.get("prediction_id"),
                "overall_outcome": prediction_data.get("overall_outcome"),
                "overall_confidence": prediction_data.get("overall_confidence"),
                "predicted_settlement_range": prediction_data.get(
                    "predicted_settlement_range"
                ),
            },
            "analysis": analysis.model_dump(mode="json"),
        }

    async def add_message(
        self, dispute_id: str, session_id: str, content: str
    ) -> Dict[str, Any]:
        session = await self._require_active_session(dispute_id)
        role = await self._get_party_role(dispute_id, session_id)

        user_message = session.add_message(
            sender_role=role,
            content=content,
            message_type=MessageType.TEXT,
        )

        ai_response = session.add_message(
            sender_role="ai_mediator",
            content="Mediator placeholder response: acknowledge positions and suggest next move.",
            message_type=MessageType.AI_MEDIATOR,
        )

        self._save_session(session)

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

    async def respond_to_offer(
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
            note = session.add_message(
                sender_role="ai_mediator",
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

    async def get_messages(
        self,
        dispute_id: str,
        since_timestamp: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        session = self._mediations.get(dispute_id)
        if not session:
            return []

        messages = session.messages
        if since_timestamp:
            messages = [m for m in messages if m.timestamp > since_timestamp]

        return [message.model_dump(mode="json") for message in messages]

    async def settle(self, dispute_id: str, amount: float) -> Dict[str, Any]:
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

    async def escalate(self, dispute_id: str) -> Dict[str, Any]:
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

    async def get_settlement(self, dispute_id: str) -> Dict[str, Any]:
        session = self._mediations.get(dispute_id)
        if not session:
            raise ValueError(f"Mediation session not found for dispute: {dispute_id}")

        if session.status != MediationStatus.SETTLED:
            raise ValueError(f"Mediation not settled for dispute: {dispute_id}")

        return {
            "dispute_id": dispute_id,
            "mediation_id": session.mediation_id,
            "status": session.status.value,
            "settlement_amount": session.settlement_amount,
            "settled_at": session.settled_at,
            "started_at": session.started_at,
            "updated_at": session.updated_at,
            "message_count": len(session.messages),
            "offer_count": len(session.offers),
        }

    async def generate_settlement_pdf(self, dispute_id: str) -> bytes:
        if dispute_id not in self._mediations:
            raise ValueError(f"Mediation session not found for dispute: {dispute_id}")

        from apps.api.src.utils.pdf_generator import generate_settlement_pdf as _gen_pdf

        settlement_data = await self.get_settlement(dispute_id)
        return _gen_pdf(settlement_data)
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

    @staticmethod
    def _find_offer(session: MediationSession, offer_id: str) -> StructuredOffer:
        for offer in session.offers:
            if offer.id == offer_id:
                return offer
        raise ValueError(f"Offer not found: {offer_id}")


def get_mediation_service() -> MediationService:
    global _mediation_service
    if _mediation_service is None:
        _mediation_service = MediationService()
    return _mediation_service
