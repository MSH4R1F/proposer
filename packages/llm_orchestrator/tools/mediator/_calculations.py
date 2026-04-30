"""Pure calculation functions lifted verbatim from MediatorAgent.

These functions are intentionally free of any LLM or I/O side-effects so they
can be tested in isolation and called deterministically from @tool wrappers.
MediatorAgent itself is left untouched in this step; Steps 5-6 will replace
its method bodies with AgentLoop runs.
"""
from __future__ import annotations

from typing import Any, Dict, Literal

from ...data.tribunal_costs import get_cost_benefit_analysis
from ...models.prediction_v2 import PredictionResult

Role = Literal["tenant", "landlord"]


def compute_zopa(prediction: PredictionResult) -> Dict[str, float]:
    """Mirror of MediatorAgent.calculate_zopa (mediator_agent.py:153-178)."""
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


def compute_counter_range(
    prediction: PredictionResult,
    current_offer: float,
    role: Role,
) -> Dict[str, float]:
    """Mirror of MediatorAgent.calculate_possible_counter_range (mediator_agent.py:122-151)."""
    if role not in ("tenant", "landlord"):
        raise ValueError(f"role must be 'tenant' or 'landlord', got {role!r}")

    zopa = compute_zopa(prediction)
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


def compute_cost_benefit(prediction: PredictionResult, role: Role) -> Dict[str, Any]:
    """Return role-specific CostBenefitAnalysis as a JSON-serializable dict.

    We always derive the settlement range from compute_zopa(prediction), even when
    prediction.predicted_settlement_range is unset and zopa was computed from a
    fallback branch (tenant_recovery_amount or deposit_at_stake). This keeps the
    framing anchored on the same number calculate_zopa reports, so settlement
    amounts presented to both parties stay numerically consistent.
    """
    if role not in ("tenant", "landlord"):
        raise ValueError(f"role must be 'tenant' or 'landlord', got {role!r}")

    zopa = compute_zopa(prediction)
    analysis = get_cost_benefit_analysis(
        role=role,
        prediction_data={"predicted_settlement_range": [zopa["min"], zopa["max"]]},
    )
    return analysis.model_dump(mode="json")
