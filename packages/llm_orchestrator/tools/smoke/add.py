from __future__ import annotations

from typing import Dict

from pydantic import BaseModel

from ...agent_loop.context import ToolContext
from ...agent_loop.tool import tool


class AddArgs(BaseModel):
    a: int
    b: int


@tool(description="Add two integers and return the sum.")
def add(ctx: ToolContext, args: AddArgs) -> Dict[str, int]:
    return {"sum": args.a + args.b}
