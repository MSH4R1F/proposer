"""Provider-neutral factory for LLM clients.

Single construction point for every LLM client in the system. Call sites pass
an :class:`LLMRole` and receive a configured :class:`BaseLLMClient` whose
provider and model are determined by ``LLMConfig`` (which in turn reads the
``LLM_<ROLE>_*`` env vars). This is what lets a single env-var flip
(``LLM_PREDICTION_PROVIDER=openai``) swap the prediction LLM without touching
service code.

For SHA-114 step 5, OpenAI dispatch is now wired: an OpenAI-backed role
returns a configured :class:`OpenAIClient`. Anthropic-backed roles continue
to return :class:`ClaudeClient`. ``store=True`` is rejected at the
:class:`OpenAIClient` constructor (privacy invariant).
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from .base import BaseLLMClient
from .claude_client import ClaudeClient
from .openai_client import OpenAIClient
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

    Dispatches to the right provider per the role's config. Anthropic roles
    return a :class:`ClaudeClient`; OpenAI roles return an
    :class:`OpenAIClient` with the role's reasoning/verbosity controls
    forwarded through.

    Args:
        role: One of the four ``LLMRole`` values.
        config: Optional ``LLMConfig`` instance; if omitted, a fresh one is
            built from environment variables.

    Returns:
        A configured ``BaseLLMClient``.
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
        # ``OpenAIClient.__init__`` rejects ``store=True``; the role config's
        # default is ``False`` and the env override is bool-coerced — no extra
        # guard needed here.
        return OpenAIClient(
            api_key=cfg.openai_api_key,
            model=role_cfg.primary_model,
            fallback_model=role_cfg.fallback_model,
            reasoning_effort=role_cfg.openai.reasoning_effort,
            text_verbosity=role_cfg.openai.text_verbosity,
            store=role_cfg.openai.store,
            max_retries=3,
        )

    raise ValueError(f"Unknown provider: {role_cfg.provider!r}")


def get_agent_turn_client(
    role: LLMRole, config: "Optional[LLMConfig]" = None
) -> "AgentTurnClient":
    """Return an ``AgentTurnClient``-shaped client for the given role.

    Both :class:`ClaudeClient` and :class:`OpenAIClient` implement the
    :class:`~llm_orchestrator.agent_loop.loop.AgentTurnClient` protocol via
    their ``run_agent_turn`` methods, so this is a thin alias around
    :func:`get_llm_client`.
    """
    client = get_llm_client(role, config=config)
    return client  # type: ignore[return-value]
