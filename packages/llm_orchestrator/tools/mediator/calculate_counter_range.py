from __future__ import annotations

from typing import Dict, Literal

from pydantic import BaseModel, Field

from ...agent_loop.context import ToolContext
from ...agent_loop.tool import tool
from ._calculations import compute_counter_range


class CounterArgs(BaseModel):
    current_offer: float = Field(..., description="The offer on the table, in GBP.")
    role: Literal["tenant", "landlord"] = Field(
        ..., description="Which party would propose the counter."
    )


@tool(description="Given a current offer and which party would respond, return the range of fair counter-offers that lie within ZOPA. Returns {min, max, center}.")
def calculate_counter_range(ctx: ToolContext, args: CounterArgs) -> Dict[str, float]:
    if ctx.prediction is None:
        raise ValueError("ToolContext.prediction is required for calculate_counter_range")
    return compute_counter_range(ctx.prediction, args.current_offer, args.role)
