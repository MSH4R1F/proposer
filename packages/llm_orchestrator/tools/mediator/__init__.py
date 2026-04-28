from __future__ import annotations

from ...agent_loop.tool import ToolSet
from .calculate_counter_range import calculate_counter_range
from .calculate_zopa import calculate_zopa
from .get_cost_benefit import get_cost_benefit

MEDIATOR_TOOLS = ToolSet(
    name="mediator",
    tools=[calculate_zopa, calculate_counter_range, get_cost_benefit],
)

__all__ = [
    "MEDIATOR_TOOLS",
    "calculate_counter_range",
    "calculate_zopa",
    "get_cost_benefit",
]
