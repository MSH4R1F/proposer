"""Provider-neutral factory for LLM clients.

For SHA-114 step 1 (foundation), the factory always returns a ``ClaudeClient``
because the OpenAI adapter does not exist yet — this file is the single
construction point that step 5 will replace with real provider dispatch. By
introducing it now, call sites that migrate ahead of step 5 (or new callers)
do not need to change again later.

If a role's config selects ``LLMProvider.OPENAI``, the factory raises
``NotImplementedError`` — this is intentional, matches §14.1 of the spec, and
will be replaced in step 3 when ``OpenAIClient`` lands.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from .base import BaseLLMClient
from .claude_client import ClaudeClient
from .types import LLMProvider, LLMRole

if TYPE_CHECKING:
    from ..agent_loop.loop import AgentTurnClient
    from ..config import LLMConfig


def _resolve_config(config: "Optional[LLMConfig]") -> "LLMConfig":
    """Lazy import + default-construct so the factory module stays import-light."""
    if config is not None:
        return config
    from ..config import LLMConfig as _LLMConfig  # local import to avoid cycles

    return _LLMConfig()


def get_llm_client(
    role: LLMRole, config: "Optional[LLMConfig]" = None
) -> BaseLLMClient:
    """Return a configured ``BaseLLMClient`` for the given role.

    Step 1: always returns a ``ClaudeClient`` for Anthropic-backed roles, with
    the role's primary/fallback model wired through from config. Raises
    ``NotImplementedError`` for OpenAI-backed roles (lands in step 3).

    Args:
        role: One of the four ``LLMRole`` values.
        config: Optional ``LLMConfig`` instance; if omitted, a fresh one is
            built from environment variables.

    Returns:
        A configured ``BaseLLMClient``. Today this is always ``ClaudeClient``.
    """
    cfg = _resolve_config(config)
    role_cfg = cfg.role_config(role)

    if role_cfg.provider == LLMProvider.ANTHROPIC:
        return ClaudeClient(
            api_key=cfg.anthropic_api_key,
            model=role_cfg.primary_model,
            fallback_model=role_cfg.fallback_model or role_cfg.primary_model,
        )

    if role_cfg.provider == LLMProvider.OPENAI:
        raise NotImplementedError(
            "OpenAIClient lands in Task 3 of SHA-114; "
            f"role={role.value} requested provider=openai"
        )

    raise ValueError(f"Unknown provider: {role_cfg.provider!r}")


def get_agent_turn_client(
    role: LLMRole, config: "Optional[LLMConfig]" = None
) -> "AgentTurnClient":
    """Return an ``AgentTurnClient``-shaped client for the given role.

    For step 1 this is the same ``ClaudeClient`` instance ``get_llm_client``
    returns — ``ClaudeClient`` already implements the ``AgentTurnClient``
    protocol via its ``run_agent_turn`` method.
    """
    client = get_llm_client(role, config=config)
    # The runtime check on AgentTurnClient verifies `run_agent_turn` is present
    # — ClaudeClient satisfies that, but step 3's OpenAIClient must too.
    return client  # type: ignore[return-value]
