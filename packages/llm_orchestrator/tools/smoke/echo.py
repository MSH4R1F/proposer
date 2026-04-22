from __future__ import annotations

from typing import Dict

from pydantic import BaseModel

from ...agent_loop.context import ToolContext
from ...agent_loop.tool import tool


class EchoArgs(BaseModel):
    message: str


@tool(description="Echo back the provided message.")
def echo(ctx: ToolContext, args: EchoArgs) -> Dict[str, str]:
    return {"echoed": args.message}
