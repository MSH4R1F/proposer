from __future__ import annotations

import json
from typing import Any, Dict, Optional, Protocol, Tuple, Union, runtime_checkable

from ..agent_loop.context import ToolContext
from ..agent_loop.loop import AgentLoop, AgentTurnClient
from ..agent_loop.trace import TraceSummary
from ..data.tribunal_costs import get_cost_benefit_analysis
from ..models.dispute import DisputeCase
from ..models.mediation import MediationMessage, StructuredOffer
from ..models.prediction_v2 import PredictionResult
from ..prompts.mediator import (
    MEDIATOR_OPENING_USER_PROMPT,
    MEDIATOR_RESPONSE_USER_PROMPT,
    MEDIATOR_SYSTEM_PROMPT,
)
from ..tools.mediator import MEDIATOR_TOOLS


@runtime_checkable
class ModelDumpable(Protocol):
    def model_dump(self, mode: str = "python") -> object: ...


MessageLike = Union[MediationMessage, Dict[str, str], str]


class MediatorAgent:
    def __init__(self, llm_client: AgentTurnClient):
        # Typed as Any so generate_response (migrated in Step 6) can still call
        # self.llm.generate(...) on the real ClaudeClient at runtime.
        self.llm: Any = llm_client
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
        messages: list[MessageLike],
        prediction: PredictionResult,
        dispute: Union[DisputeCase, dict[str, object]],
        latest_offer: Optional[StructuredOffer] = None,
    ) -> str:
        self._stats["messages_processed"] += 1
        zopa = self.calculate_zopa(prediction)

        responding_role = "tenant"
        offer_amount: Optional[float] = None
        if latest_offer is not None:
            responding_role = (
                "landlord" if latest_offer.proposed_by_role == "tenant" else "tenant"
            )
            offer_amount = latest_offer.amount

        possible_counter_range: Optional[dict[str, float]] = None
        if offer_amount is not None:
            possible_counter_range = self.calculate_possible_counter_range(
                prediction=prediction,
                current_offer=offer_amount,
                role=responding_role,
            )

        cost_context = {
            "tenant": get_cost_benefit_analysis(
                role="tenant",
                prediction_data={
                    "predicted_settlement_range": [zopa["min"], zopa["max"]]
                },
            ).model_dump(mode="json"),
            "landlord": get_cost_benefit_analysis(
                role="landlord",
                prediction_data={
                    "predicted_settlement_range": [zopa["min"], zopa["max"]]
                },
            ).model_dump(mode="json"),
        }

        user_prompt = MEDIATOR_RESPONSE_USER_PROMPT.format(
            dispute_context=self._to_json(dispute),
            overall_outcome=prediction.overall_outcome.value,
            confidence_score=f"{prediction.overall_confidence:.0%}",
            settlement_range=self._format_range(prediction.predicted_settlement_range),
            key_strengths=self._format_list(prediction.key_strengths),
            key_weaknesses=self._format_list(prediction.key_weaknesses),
            retrieved_cases=self._format_list(prediction.retrieved_cases),
            zopa=json.dumps(zopa),
            latest_offer=self._to_json(latest_offer),
            possible_counter_range=self._to_json(possible_counter_range),
            cost_context=self._to_json(cost_context),
            recent_messages=self._format_messages(messages),
        )

        response = await self.llm.generate(
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=MEDIATOR_SYSTEM_PROMPT,
            max_tokens=900,
            temperature=0.5,
        )
        return response

    def calculate_possible_counter_range(
        self,
        prediction: PredictionResult,
        current_offer: float,
        role: str,
    ) -> dict[str, float]:
        zopa = self.calculate_zopa(prediction)
        zopa_min = zopa["min"]
        zopa_max = zopa["max"]
        offer = float(current_offer)

        if role == "tenant":
            min_value = max(offer, zopa_min)
            max_value = zopa_max
            if min_value > max_value:
                min_value = zopa_max
                max_value = zopa_max
        else:
            min_value = zopa_min
            max_value = min(offer, zopa_max)
            if min_value > max_value:
                min_value = zopa_min
                max_value = zopa_min

        center = (min_value + max_value) / 2
        return {
            "min": round(min_value, 2),
            "max": round(max_value, 2),
            "center": round(center, 2),
        }

    def calculate_zopa(self, prediction: PredictionResult) -> dict[str, float]:
        range_data = prediction.predicted_settlement_range

        if range_data and len(range_data) == 2:
            lower = float(min(range_data[0], range_data[1]))
            upper = float(max(range_data[0], range_data[1]))
        elif prediction.tenant_recovery_amount is not None:
            base = float(prediction.tenant_recovery_amount)
            spread = max(base * 0.1, 25.0)
            lower = max(base - spread, 0.0)
            upper = base + spread
        elif prediction.deposit_at_stake is not None:
            base = float(prediction.deposit_at_stake) * 0.5
            spread = max(base * 0.15, 25.0)
            lower = max(base - spread, 0.0)
            upper = base + spread
        else:
            lower = 0.0
            upper = 0.0

        center = (lower + upper) / 2
        return {
            "min": round(lower, 2),
            "max": round(upper, 2),
            "center": round(center, 2),
        }

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

    def _format_range(self, settlement_range: Optional[tuple[float, float]]) -> str:
        if settlement_range and len(settlement_range) == 2:
            return (
                f"£{float(settlement_range[0]):.2f} - £{float(settlement_range[1]):.2f}"
            )
        zopa = self.calculate_zopa_proxy(settlement_range)
        return f"£{zopa['min']:.2f} - £{zopa['max']:.2f}"

    def calculate_zopa_proxy(
        self,
        settlement_range: Optional[tuple[float, float]],
    ) -> dict[str, float]:
        if settlement_range and len(settlement_range) == 2:
            low = float(min(settlement_range[0], settlement_range[1]))
            high = float(max(settlement_range[0], settlement_range[1]))
            return {"min": low, "max": high}
        return {"min": 0.0, "max": 0.0}

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
