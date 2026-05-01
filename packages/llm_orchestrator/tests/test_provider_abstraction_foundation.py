"""Foundation-level tests for SHA-114 (LLM provider abstraction, step 1).

Covers:
- ``LLMProvider`` / ``LLMRole`` enum values + string-coercion behaviour.
- Provider-neutral exception hierarchy.
- ``LLMRoleConfig`` / ``OpenAIControls`` validation.
- ``LLMConfig`` defaults, env-var overrides, conditional API-key validation.
- Pricing YAML round-trip via the loader.
- Factory returns a ``ClaudeClient`` for every role under default env, with
  the correct primary/fallback model from the role config.
- ``ClientStats`` schema additions (provider, model, cached_tokens_in,
  reasoning_tokens_out, estimated_cost_usd).
- Guard test that asserts the count of direct ``ClaudeClient(`` constructions
  matches today's allowlist.

No behaviour change should be visible to call sites; these tests pin the
contract so step 5 can swap the factory wiring confidently.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from llm_orchestrator.clients import _pricing
from llm_orchestrator.clients.claude_client import ClaudeClient
from llm_orchestrator.clients.exceptions import (
    LLMAPIError,
    LLMError,
    LLMIncompleteResponseError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMStructuredOutputError,
)
from llm_orchestrator.clients.factory import (
    get_agent_turn_client,
    get_llm_client,
)
from llm_orchestrator.clients.openai_client import OpenAIClient
from llm_orchestrator.clients.types import LLMProvider, LLMRole
from llm_orchestrator.config import (
    LLMConfig,
    LLMRoleConfig,
    OpenAIControls,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


def test_llm_provider_values() -> None:
    assert LLMProvider.ANTHROPIC.value == "anthropic"
    assert LLMProvider.OPENAI.value == "openai"
    assert LLMProvider("anthropic") is LLMProvider.ANTHROPIC
    assert LLMProvider("openai") is LLMProvider.OPENAI


def test_llm_role_values() -> None:
    assert {r.value for r in LLMRole} == {
        "intake",
        "prediction",
        "mediator",
        "extraction",
    }


def test_llm_role_string_coercion() -> None:
    # str-Enum so equality with raw strings works for config dict access.
    assert LLMRole.INTAKE == "intake"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


def test_exception_hierarchy_inherits_from_llm_error() -> None:
    for exc in (
        LLMRateLimitError,
        LLMAPIError,
        LLMStructuredOutputError,
        LLMRefusalError,
        LLMIncompleteResponseError,
    ):
        assert issubclass(exc, LLMError)
    assert issubclass(LLMError, Exception)


def test_exception_can_be_raised_and_caught_as_neutral_type() -> None:
    with pytest.raises(LLMError):
        raise LLMRateLimitError("rate-limited")
    with pytest.raises(LLMError):
        raise LLMAPIError("oops")


# ---------------------------------------------------------------------------
# OpenAIControls + LLMRoleConfig
# ---------------------------------------------------------------------------


def test_openai_controls_defaults() -> None:
    ctrl = OpenAIControls()
    assert ctrl.reasoning_effort is None
    assert ctrl.text_verbosity is None
    assert ctrl.store is False


@pytest.mark.parametrize(
    "value", ["none", "low", "medium", "high", "xhigh"]
)
def test_openai_controls_reasoning_effort_accepts_allowed(value: str) -> None:
    ctrl = OpenAIControls(reasoning_effort=value)
    assert ctrl.reasoning_effort == value


def test_openai_controls_reasoning_effort_rejects_unknown() -> None:
    with pytest.raises(ValidationError):
        OpenAIControls(reasoning_effort="extreme")


def test_openai_controls_text_verbosity_rejects_unknown() -> None:
    with pytest.raises(ValidationError):
        OpenAIControls(text_verbosity="silent")


def test_llm_role_config_min_construct() -> None:
    cfg = LLMRoleConfig(
        provider=LLMProvider.ANTHROPIC,
        primary_model="claude-sonnet-4-20250514",
    )
    assert cfg.provider == LLMProvider.ANTHROPIC
    assert cfg.primary_model == "claude-sonnet-4-20250514"
    assert cfg.fallback_model is None
    assert cfg.max_output_tokens == 4096
    assert cfg.temperature == pytest.approx(0.7)
    assert isinstance(cfg.openai, OpenAIControls)


def test_llm_role_config_temperature_bounds() -> None:
    with pytest.raises(ValidationError):
        LLMRoleConfig(
            provider=LLMProvider.ANTHROPIC,
            primary_model="claude-sonnet-4-20250514",
            temperature=1.5,
        )


# ---------------------------------------------------------------------------
# LLMConfig defaults + env overrides + key validation
# ---------------------------------------------------------------------------


@pytest.fixture
def clean_env(monkeypatch):
    """Strip all LLM_<ROLE>_* and provider-key env vars for deterministic defaults."""
    for key in list(__import__("os").environ.keys()):
        if key.startswith("LLM_") or key in {
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
        }:
            monkeypatch.delenv(key, raising=False)
    return monkeypatch


def test_llm_config_default_uses_anthropic_for_every_role(clean_env) -> None:
    """Default env -> all four roles route to Anthropic with §7 model defaults."""
    cfg = LLMConfig()
    assert cfg.intake.provider == LLMProvider.ANTHROPIC
    assert cfg.prediction.provider == LLMProvider.ANTHROPIC
    assert cfg.mediator.provider == LLMProvider.ANTHROPIC
    assert cfg.extraction.provider == LLMProvider.ANTHROPIC

    assert cfg.prediction.primary_model == "claude-sonnet-4-20250514"
    assert cfg.mediator.primary_model == "claude-sonnet-4-20250514"
    assert cfg.intake.primary_model == "claude-3-5-haiku-20241022"
    assert cfg.extraction.primary_model == "claude-3-5-haiku-20241022"


def test_llm_config_role_env_overrides_apply(clean_env) -> None:
    clean_env.setenv("LLM_PREDICTION_PRIMARY_MODEL", "claude-test-primary")
    clean_env.setenv("LLM_PREDICTION_FALLBACK_MODEL", "claude-test-fallback")
    clean_env.setenv("LLM_PREDICTION_MAX_OUTPUT_TOKENS", "2048")

    cfg = LLMConfig()
    assert cfg.prediction.primary_model == "claude-test-primary"
    assert cfg.prediction.fallback_model == "claude-test-fallback"
    assert cfg.prediction.max_output_tokens == 2048


def test_llm_config_openai_role_requires_openai_key(clean_env) -> None:
    """If a role opts into OpenAI but OPENAI_API_KEY is absent, validation hard-fails."""
    clean_env.setenv("LLM_PREDICTION_PROVIDER", "openai")
    # No OPENAI_API_KEY set.
    with pytest.raises(ValidationError) as excinfo:
        LLMConfig()
    assert "OPENAI_API_KEY" in str(excinfo.value)


def test_llm_config_openai_role_with_key_constructs(clean_env) -> None:
    clean_env.setenv("LLM_PREDICTION_PROVIDER", "openai")
    clean_env.setenv("OPENAI_API_KEY", "sk-test-123")

    cfg = LLMConfig()
    assert cfg.prediction.provider == LLMProvider.OPENAI
    # OpenAI primary should default to gpt-5.5 per §7.
    assert cfg.prediction.primary_model == "gpt-5.5"
    # OpenAIControls defaults applied.
    assert cfg.prediction.openai.reasoning_effort == "high"
    assert cfg.prediction.openai.text_verbosity == "medium"


def test_llm_config_anthropic_default_does_not_hard_fail_without_key(clean_env) -> None:
    """Default env (anthropic everywhere) must construct without exploding,
    matching pre-SHA-114 warn-only behaviour for missing ANTHROPIC_API_KEY."""
    cfg = LLMConfig()  # no ANTHROPIC_API_KEY in env
    # Construction must succeed; warn-only is fine.
    assert cfg.anthropic_api_key == ""


def test_llm_config_invalid_provider_env_value(clean_env) -> None:
    clean_env.setenv("LLM_INTAKE_PROVIDER", "huggingface")
    with pytest.raises((ValueError, ValidationError)):
        LLMConfig()


def test_llm_config_empty_string_env_vars_fall_back_to_defaults(clean_env) -> None:
    """``FOO=""`` must be treated as unset for every per-role env override —
    not just the model-name ones that fall back via truthiness. Previously,
    ``LLM_INTAKE_REASONING_EFFORT=""`` would be forwarded to the validator
    and crash."""
    clean_env.setenv("LLM_INTAKE_PRIMARY_MODEL", "")
    clean_env.setenv("LLM_INTAKE_FALLBACK_MODEL", "")
    clean_env.setenv("LLM_INTAKE_REASONING_EFFORT", "")
    clean_env.setenv("LLM_INTAKE_TEXT_VERBOSITY", "")
    clean_env.setenv("LLM_INTAKE_STORE", "")
    clean_env.setenv("LLM_INTAKE_MAX_OUTPUT_TOKENS", "")

    cfg = LLMConfig()
    # Default Anthropic models for INTAKE per §7.
    assert cfg.intake.provider == LLMProvider.ANTHROPIC
    assert cfg.intake.primary_model == "claude-3-5-haiku-20241022"
    assert cfg.intake.fallback_model == "claude-3-5-haiku-20241022"
    assert cfg.intake.max_output_tokens == 4096
    # Anthropic role -> OpenAI knobs default to None / False.
    assert cfg.intake.openai.reasoning_effort is None
    assert cfg.intake.openai.text_verbosity is None
    assert cfg.intake.openai.store is False


def test_llm_config_invalid_max_output_tokens_env_raises_role_named_error(
    clean_env,
) -> None:
    """Bad ``LLM_<ROLE>_MAX_OUTPUT_TOKENS`` must raise a clear, role-named
    error — previously it leaked a bare ``invalid literal for int()`` from
    Python's stdlib with no context about which role was misconfigured."""
    clean_env.setenv("LLM_INTAKE_MAX_OUTPUT_TOKENS", "abc")
    with pytest.raises((ValueError, ValidationError)) as excinfo:
        LLMConfig()
    msg = str(excinfo.value)
    assert "LLM_INTAKE_MAX_OUTPUT_TOKENS" in msg
    assert "abc" in msg


def test_llm_config_role_config_lookup(clean_env) -> None:
    cfg = LLMConfig()
    assert cfg.role_config(LLMRole.PREDICTION) is cfg.prediction
    assert cfg.role_config(LLMRole.INTAKE) is cfg.intake


def test_llm_config_legacy_flat_fields_preserved(clean_env) -> None:
    """Step 1 must not break call sites still using the flat fields."""
    cfg = LLMConfig()
    assert cfg.primary_model == "claude-sonnet-4-20250514"
    assert cfg.fallback_model == "claude-3-5-haiku-20241022"
    assert cfg.max_tokens == 4096
    assert cfg.temperature == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# Pricing YAML loader
# ---------------------------------------------------------------------------


def test_pricing_yaml_loads_successfully() -> None:
    _pricing.load_pricing.cache_clear()
    data = _pricing.load_pricing()
    assert "anthropic" in data
    assert "openai" in data
    assert data["metadata"]["units"] == "usd_per_1m_tokens"


def test_pricing_lookup_anthropic() -> None:
    _pricing.load_pricing.cache_clear()
    pricing = _pricing.get_model_pricing(
        LLMProvider.ANTHROPIC, "claude-sonnet-4-20250514"
    )
    assert pricing is not None
    assert pricing["input"] == pytest.approx(3.0)
    assert pricing["output"] == pytest.approx(15.0)


def test_pricing_lookup_openai_short_context_tier() -> None:
    _pricing.load_pricing.cache_clear()
    pricing = _pricing.get_model_pricing(LLMProvider.OPENAI, "gpt-5.5")
    assert pricing is not None
    assert pricing["input_short_context"] == pytest.approx(2.5)
    assert pricing["output_long_context"] == pytest.approx(22.5)


def test_pricing_lookup_unknown_model_returns_none() -> None:
    _pricing.load_pricing.cache_clear()
    assert (
        _pricing.get_model_pricing(LLMProvider.ANTHROPIC, "no-such-model") is None
    )


def test_pricing_lookup_unknown_model_warns_once_per_process(monkeypatch) -> None:
    """A missing pricing entry must surface exactly one warning per (provider, model)
    so a model-name typo doesn't make cost tracking go silently dark — but also
    doesn't spam the log on every ``get_stats()`` call."""
    _pricing.load_pricing.cache_clear()
    _pricing._warned_missing_pricing.clear()

    calls: list[dict] = []

    def fake_warning(event: str, **kw) -> None:
        calls.append({"event": event, **kw})

    monkeypatch.setattr(_pricing._logger, "warning", fake_warning)

    assert (
        _pricing.get_model_pricing(LLMProvider.ANTHROPIC, "definitely-not-a-model")
        is None
    )
    assert (
        _pricing.get_model_pricing(LLMProvider.ANTHROPIC, "definitely-not-a-model")
        is None
    )

    pricing_warnings = [c for c in calls if c["event"] == "pricing_missing_for_model"]
    assert len(pricing_warnings) == 1, pricing_warnings
    assert pricing_warnings[0]["provider"] == "anthropic"
    assert pricing_warnings[0]["model"] == "definitely-not-a-model"


def test_anthropic_pricing_table_shape_matches_legacy() -> None:
    """The compat shim must yield the same shape ClaudeClient.PRICING used to expose."""
    _pricing.load_pricing.cache_clear()
    table = _pricing.get_anthropic_pricing_table()
    assert "claude-sonnet-4-20250514" in table
    assert set(table["claude-sonnet-4-20250514"].keys()) == {"input", "output"}


def test_claude_client_pricing_compat_shim_works() -> None:
    """Existing ClaudeClient.PRICING['<model>']['input'] still works."""
    assert "claude-sonnet-4-20250514" in ClaudeClient.PRICING
    assert ClaudeClient.PRICING["claude-sonnet-4-20250514"]["input"] == pytest.approx(
        3.0
    )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_factory_returns_claude_client_for_every_role_under_default_env(
    clean_env,
) -> None:
    cfg = LLMConfig(anthropic_api_key="dummy")
    for role in LLMRole:
        client = get_llm_client(role, config=cfg)
        assert isinstance(client, ClaudeClient), role


def test_factory_wires_role_primary_and_fallback_models(clean_env) -> None:
    cfg = LLMConfig(anthropic_api_key="dummy")
    client = get_llm_client(LLMRole.PREDICTION, config=cfg)
    assert isinstance(client, ClaudeClient)
    assert client.model == "claude-sonnet-4-20250514"
    assert client.fallback_model == "claude-3-5-haiku-20241022"

    client_intake = get_llm_client(LLMRole.INTAKE, config=cfg)
    assert client_intake.model == "claude-3-5-haiku-20241022"


def test_factory_returns_openai_client_for_openai_role(clean_env) -> None:
    clean_env.setenv("LLM_PREDICTION_PROVIDER", "openai")
    clean_env.setenv("OPENAI_API_KEY", "sk-test")
    cfg = LLMConfig(anthropic_api_key="dummy")
    client = get_llm_client(LLMRole.PREDICTION, config=cfg)
    assert isinstance(client, OpenAIClient)
    assert client.model == "gpt-5.5"
    assert client.fallback_model == "gpt-5.4"
    assert client.reasoning_effort == "high"
    assert client.text_verbosity == "medium"


def test_get_agent_turn_client_returns_runtime_compatible_client(clean_env) -> None:
    """The returned client must satisfy AgentTurnClient (has run_agent_turn)."""
    cfg = LLMConfig(anthropic_api_key="dummy")
    client = get_agent_turn_client(LLMRole.MEDIATOR, config=cfg)
    assert hasattr(client, "run_agent_turn")


def test_get_agent_turn_client_supports_openai_roles(clean_env) -> None:
    clean_env.setenv("LLM_MEDIATOR_PROVIDER", "openai")
    clean_env.setenv("OPENAI_API_KEY", "sk-test")
    cfg = LLMConfig(anthropic_api_key="dummy")
    client = get_agent_turn_client(LLMRole.MEDIATOR, config=cfg)
    assert isinstance(client, OpenAIClient)
    assert hasattr(client, "run_agent_turn")


# ---------------------------------------------------------------------------
# ClientStats additions
# ---------------------------------------------------------------------------


def test_claude_client_stats_includes_new_fields() -> None:
    client = ClaudeClient(api_key="dummy", model="claude-sonnet-4-20250514")
    stats = client.get_stats()
    # Legacy fields preserved.
    for key in ("calls", "tokens_in", "tokens_out", "errors", "fallback_uses"):
        assert key in stats
    # New SHA-114 fields.
    assert stats["provider"] == "anthropic"
    assert stats["model"] == "claude-sonnet-4-20250514"
    assert stats["cached_tokens_in"] == 0
    assert stats["reasoning_tokens_out"] == 0
    assert stats["estimated_cost_usd"] == pytest.approx(0.0)


def test_claude_client_reset_stats_preserves_new_fields() -> None:
    client = ClaudeClient(api_key="dummy")
    client._stats["tokens_in"] = 999  # type: ignore[index]
    client.reset_stats()
    stats = client.get_stats()
    assert stats["tokens_in"] == 0
    assert stats["cached_tokens_in"] == 0
    assert stats["reasoning_tokens_out"] == 0


# ---------------------------------------------------------------------------
# Guard test — direct ClaudeClient( construction count
# ---------------------------------------------------------------------------


# Allowlist of (file, count) pairs that are still permitted to construct
# ClaudeClient directly after step 5. Production code must go through the
# role-aware factory; only focused client tests and the factory itself are
# allowed to mention the constructor directly.
#
# Captured 2026-05-01 by ripgrep `ClaudeClient\(` excluding only the
# ClaudeClient implementation module itself.
_ALLOWED_DIRECT_CONSTRUCTIONS: dict[str, int] = {
    "packages/llm_orchestrator/clients/factory.py": 1,
    "packages/llm_orchestrator/tests/test_claude_client_agent_turn.py": 1,
    "packages/llm_orchestrator/tests/test_openai_client_agent_turn.py": 1,
    "packages/llm_orchestrator/tests/test_provider_abstraction_foundation.py": 6,
}


def _repo_root() -> Path:
    # Walk up from this test file until we find the worktree root (has 'apps/' and
    # 'packages/').
    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        if (parent / "apps").is_dir() and (parent / "packages").is_dir():
            return parent
    raise RuntimeError("Could not locate worktree root from test file path")


def test_guard_direct_claude_client_construction_count() -> None:
    """Tripwire: any new direct `ClaudeClient(` outside the client module
    or tests must be added to ``_ALLOWED_DIRECT_CONSTRUCTIONS`` (and ideally
    removed in step 5). Prevents silent regressions during migration."""
    root = _repo_root()
    pattern = re.compile(r"\bClaudeClient\s*\(")

    found: dict[str, int] = {}
    for ext_dir in ("apps", "packages", "scripts"):
        base = root / ext_dir
        if not base.is_dir():
            continue
        for py in base.rglob("*.py"):
            rel = py.relative_to(root).as_posix()
            # Skip the client implementation itself; the factory and focused
            # tests remain counted via the allowlist above.
            if rel == "packages/llm_orchestrator/clients/claude_client.py":
                continue
            text = py.read_text(encoding="utf-8", errors="replace")
            n = len(pattern.findall(text))
            if n:
                found[rel] = n

    assert found == _ALLOWED_DIRECT_CONSTRUCTIONS, (
        "Direct ClaudeClient( constructions changed.\n"
        f"  Expected: {_ALLOWED_DIRECT_CONSTRUCTIONS}\n"
        f"  Found:    {found}\n"
        "If this is intentional, update _ALLOWED_DIRECT_CONSTRUCTIONS; "
        "otherwise route the new construction through "
        "llm_orchestrator.clients.factory.get_llm_client()."
    )
