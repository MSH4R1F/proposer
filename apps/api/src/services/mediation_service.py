import fcntl
import json
import os
from typing import Any, Dict, List, Optional

import structlog

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

_mediation_service: Optional["MediationService"] = None


class MediationService:
    def __init__(self):
        logger.debug("initializing_mediation_service")
        from llm_orchestrator.config import LLMConfig

        llm_config = LLMConfig.from_env()
        self._mediator = self._build_mediator_agent(llm_config.anthropic_api_key)
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

    @staticmethod
    def _build_mediator_agent(api_key: str) -> Any:
        from llm_orchestrator.agents.mediator_agent import MediatorAgent
        from llm_orchestrator.clients.claude_client import ClaudeClient

        if api_key:
            return MediatorAgent(ClaudeClient(api_key=api_key))
        logger.warning("mediator_llm_key_missing_using_deterministic_fallback")
        return MediatorAgent(_DeterministicMediatorLLM())

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
        return {
            "party_role": role,
            "analysis": analysis.model_dump(mode="json"),
            "prediction_summary": {
                "prediction_id": prediction_data.get("prediction_id"),
                "overall_outcome": prediction_data.get("overall_outcome"),
                "overall_confidence": prediction_data.get("overall_confidence"),
                "predicted_settlement_range": prediction_data.get(
                    "predicted_settlement_range"
                ),
            },
        }

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
        # Either way, the fallback message below keeps the mediation session valid.
        trace_summary: Optional[TraceSummary] = None
        try:
            initial_content, trace_summary = await self._mediator.generate_opening_message(
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

        try:
            ai_content = await self._mediator.generate_response(
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


class _DeterministicMediatorLLM:
    async def generate(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        _ = (system_prompt, max_tokens, temperature)
        prompt = messages[-1]["content"].lower() if messages else ""
        if "opening mediation message" in prompt:
            return (
                "Welcome to mediation. I will share neutral information from similar "
                "tribunal outcomes, summarize both perspectives, and help identify a "
                "practical negotiation range."
            )
        return (
            "I have noted both positions. Based on comparable tribunal outcomes, it may "
            "be useful to test the latest offer against the likely settlement range and "
            "focus on evidence each side can verify."
        )
