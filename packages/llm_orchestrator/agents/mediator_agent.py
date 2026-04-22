from __future__ import annotations

import json
from typing import Dict, Optional, Protocol, Tuple, Union, runtime_checkable

from ..agent_loop.context import ToolContext
from ..agent_loop.loop import AgentLoop, AgentTurnClient
from ..agent_loop.trace import TraceSummary
from ..models.dispute import DisputeCase
from ..models.mediation import MediationMessage, StructuredOffer
from ..models.prediction_v2 import PredictionResult
from ..prompts.mediator import MEDIATOR_SYSTEM_PROMPT
from ..tools.mediator import MEDIATOR_TOOLS


@runtime_checkable
class ModelDumpable(Protocol):
    def model_dump(self, mode: str = "python") -> object: ...


MessageLike = Union[MediationMessage, Dict[str, str], str]


class MediatorAgent:
    def __init__(self, llm_client: AgentTurnClient):
        self.llm: AgentTurnClient = llm_client
        self._stats: Dict[str, int] = {"messages_processed": 0}

    async def generate_opening_message(
        self,
        prediction: PredictionResult,
        dispute: Union[DisputeCase, object],
        expectation_data_tenant: Dict[str, object],
        expectation_data_landlord: Dict[str, object],
    ) -> Tuple[str, TraceSummary]:
        dispute_id: Optional[str] = (
            dispute.dispute_id if isinstance(dispute, DisputeCase) else None
        )
        ctx = ToolContext(prediction=prediction, dispute_id=dispute_id)

        user_prompt = (
            "A new mediation session is starting. Use the tools when you need numbers.\n\n"
            "Dispute context:\n"
            f"{self._to_json(dispute)}\n\n"
            "Prediction (top-level info only — call calculate_zopa() for the range):\n"
            f"- Outcome: {prediction.overall_outcome.value}\n"
            f"- Confidence: {prediction.overall_confidence:.0%}\n"
            f"- Key strengths: {self._format_list(prediction.key_strengths)}\n"
            f"- Key weaknesses: {self._format_list(prediction.key_weaknesses)}\n"
            f"- Retrieved cases: {self._format_list(prediction.retrieved_cases)}\n\n"
            "Tenant's stated expectation:\n"
            f"{self._to_json(expectation_data_tenant)}\n\n"
            "Landlord's stated expectation:\n"
            f"{self._to_json(expectation_data_landlord)}\n\n"
            "Write the opening message for the shared thread now."
        )

        loop = AgentLoop(
            llm_client=self.llm,
            tool_set=MEDIATOR_TOOLS,
            max_turns=6,
            max_tokens=900,
        )
        result = await loop.run(
            system_prompt=MEDIATOR_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            ctx=ctx,
        )
        return (result.final_text or "", result.trace)

    async def generate_response(
        self,
        messages: list,
        prediction: PredictionResult,
        dispute: Union[DisputeCase, object],
        latest_offer: Optional[StructuredOffer] = None,
    ) -> Tuple[str, TraceSummary]:
        self._stats["messages_processed"] += 1

        dispute_id: Optional[str] = (
            dispute.dispute_id if isinstance(dispute, DisputeCase) else None
        )
        ctx = ToolContext(prediction=prediction, dispute_id=dispute_id)

        user_prompt = (
            "Continue the mediation. Use the tools if you need numbers.\n\n"
            "Recent conversation:\n"
            f"{self._format_messages(messages)}\n\n"
            "Latest offer:\n"
            f"{self._to_json(latest_offer)}\n\n"
            "Dispute context:\n"
            f"{self._to_json(dispute)}\n\n"
            "Prediction (top-level info only — call tools for settlement numbers):\n"
            f"- Outcome: {prediction.overall_outcome.value}\n"
            f"- Confidence: {prediction.overall_confidence:.0%}\n"
            f"- Key strengths: {self._format_list(prediction.key_strengths)}\n"
            f"- Key weaknesses: {self._format_list(prediction.key_weaknesses)}\n"
            f"- Retrieved cases: {self._format_list(prediction.retrieved_cases)}\n\n"
            "Continue the mediation with the next response. Use the tools if you need numbers."
        )

        loop = AgentLoop(
            llm_client=self.llm,
            tool_set=MEDIATOR_TOOLS,
            max_turns=8,
            max_tokens=900,
        )
        result = await loop.run(
            system_prompt=MEDIATOR_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            ctx=ctx,
        )
        return (result.final_text or "", result.trace)

    def get_stats(self) -> dict[str, object]:
        llm_stats: object = (
            self.llm.get_stats() if hasattr(self.llm, "get_stats") else {}
        )
        return {
            **self._stats,
            "llm_stats": llm_stats,
        }

    def _format_messages(self, messages: list[MessageLike]) -> str:
        lines: list[str] = []
        for message in messages[-12:]:
            if isinstance(message, MediationMessage):
                lines.append(f"{message.sender_role}: {message.content}")
                continue
            if isinstance(message, dict):
                role = message.get("sender_role") or message.get("role") or "party"
                content = message.get("content", "")
                lines.append(f"{role}: {content}")
                continue
            lines.append(str(message))
        return "\n".join(lines)

    def _format_list(self, values: list[str]) -> str:
        if not values:
            return "None provided"
        return "; ".join(values)

    def _to_json(self, value: object) -> str:
        if value is None:
            return "null"
        if isinstance(value, ModelDumpable):
            model_data = value.model_dump(mode="json")
            return json.dumps(model_data, ensure_ascii=True, default=str)
        return json.dumps(value, ensure_ascii=True, default=str)
