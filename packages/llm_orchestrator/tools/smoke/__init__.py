from __future__ import annotations

from ...agent_loop.tool import ToolSet
from .add import add
from .echo import echo

SMOKE_TOOLS = ToolSet(name="smoke", tools=[echo, add])

__all__ = ["echo", "add", "SMOKE_TOOLS"]
