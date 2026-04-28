from __future__ import annotations

from typing import Dict

from pydantic import BaseModel

from ...agent_loop.context import ToolContext
from ...agent_loop.tool import tool
from ._calculations import compute_zopa


class ZopaArgs(BaseModel):
    """No arguments — the tool reads the dispute's prediction from ToolContext."""


@tool(description="Calculate the Zone of Possible Agreement from the dispute's prediction. Returns {min, max, center} in GBP.")
def calculate_zopa(ctx: ToolContext, args: ZopaArgs) -> Dict[str, float]:
    if ctx.prediction is None:
        raise ValueError("ToolContext.prediction is required for calculate_zopa")
    return compute_zopa(ctx.prediction)
