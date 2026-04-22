from __future__ import annotations

from typing import Any, Dict, Literal

from pydantic import BaseModel

from ...agent_loop.context import ToolContext
from ...agent_loop.tool import tool
from ._calculations import compute_cost_benefit


class CostBenefitArgs(BaseModel):
    role: Literal["tenant", "landlord"]


@tool(description="Return the role-specific settlement-vs-tribunal cost-benefit framing — costs, timeline, and qualitative risks for the chosen party.")
def get_cost_benefit(ctx: ToolContext, args: CostBenefitArgs) -> Dict[str, Any]:
    if ctx.prediction is None:
        raise ValueError("ToolContext.prediction is required for get_cost_benefit")
    return compute_cost_benefit(ctx.prediction, args.role)
