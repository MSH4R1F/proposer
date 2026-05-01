"""Pricing YAML loader for LLM client cost estimation.

Loads ``packages/llm_orchestrator/config/pricing.yaml`` once on first access
and exposes a thin API for looking up pricing by ``(provider, model)``.

This module replaces the inline ``ClaudeClient.PRICING`` dict so adding a new
provider/model is a YAML edit rather than a code edit. ``ClaudeClient.PRICING``
is preserved as a thin compatibility shim that reads from this loader so
existing tests keep passing.

Introduced for SHA-114 (LLM provider abstraction). See
``docs/superpowers/specs/2026-05-01-llm-provider-abstraction-design.md`` §9.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .types import LLMProvider

# Path to the pricing YAML, anchored relative to this file (works regardless
# of cwd or how the package is installed).
PRICING_YAML_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "pricing.yaml"
)


@lru_cache(maxsize=1)
def load_pricing(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load and cache the pricing YAML.

    The default path is the repo's ``config/pricing.yaml``. ``path`` is exposed
    for tests that want to load a fixture YAML.

    Returns the full parsed dict so callers can access the ``metadata`` block
    if needed.
    """
    target = path or PRICING_YAML_PATH
    with open(target, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Pricing YAML at {target} did not parse to a dict")
    return data


def get_model_pricing(
    provider: LLMProvider, model: str, *, path: Optional[Path] = None
) -> Optional[Dict[str, float]]:
    """Look up pricing for a single ``(provider, model)`` pair.

    Returns the pricing dict for the model (e.g. ``{"input": 3.0, "output": 15.0}``
    for Anthropic, or the more elaborate OpenAI schema with context tiers) or
    ``None`` if the model is unknown.

    This is the primary lookup used by ``ClientStats.estimated_cost_usd``.
    """
    data = load_pricing(path)
    provider_block = data.get(provider.value)
    if not isinstance(provider_block, dict):
        return None
    model_pricing = provider_block.get(model)
    if not isinstance(model_pricing, dict):
        return None
    return dict(model_pricing)


def get_anthropic_pricing_table(
    *, path: Optional[Path] = None
) -> Dict[str, Dict[str, float]]:
    """Return the full Anthropic pricing table (compat shim for ClaudeClient.PRICING).

    Returned dict has the same shape ClaudeClient previously hard-coded:
    ``{model_name: {"input": float, "output": float}}``.
    """
    data = load_pricing(path)
    block = data.get("anthropic") or {}
    if not isinstance(block, dict):
        return {}
    return {
        model: {k: float(v) for k, v in pricing.items()}
        for model, pricing in block.items()
        if isinstance(pricing, dict)
    }
