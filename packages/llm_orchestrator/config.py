"""
Configuration for the LLM Orchestrator package.

Manages API keys, model settings, and runtime configuration.

For SHA-114 (LLM provider abstraction), per-role provider/model configuration
was added on top of the existing flat fields. The flat fields
(``primary_model``, ``fallback_model``, ``max_tokens``, ``temperature``,
``anthropic_api_key``, ``openai_api_key``, etc.) are preserved for
back-compat — Task 5 will migrate call sites to the role-aware fields.
"""

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator

from .clients.types import LLMProvider, LLMRole


# --- Per-role default models -------------------------------------------------
#
# Source: spec §7. Defaults keep current behaviour (Anthropic everywhere) so
# existing call sites continue to work unchanged. OpenAI defaults are stored
# alongside so a single env-var flip (``LLM_<ROLE>_PROVIDER=openai``) selects
# OpenAI without further config.

_ROLE_DEFAULTS: dict[LLMRole, dict] = {
    LLMRole.PREDICTION: {
        "provider": LLMProvider.ANTHROPIC,
        "anthropic_primary": "claude-sonnet-4-20250514",
        "anthropic_fallback": "claude-3-5-haiku-20241022",
        "openai_primary": "gpt-5.5",
        "openai_fallback": "gpt-5.4",
        "openai_reasoning_effort": "high",
        "openai_text_verbosity": "medium",
    },
    LLMRole.MEDIATOR: {
        "provider": LLMProvider.ANTHROPIC,
        "anthropic_primary": "claude-sonnet-4-20250514",
        "anthropic_fallback": "claude-3-5-haiku-20241022",
        "openai_primary": "gpt-5.4",
        "openai_fallback": "gpt-5.4-mini",
        "openai_reasoning_effort": "medium",
        "openai_text_verbosity": "low",
    },
    LLMRole.INTAKE: {
        "provider": LLMProvider.ANTHROPIC,
        "anthropic_primary": "claude-3-5-haiku-20241022",
        "anthropic_fallback": "claude-3-5-haiku-20241022",
        "openai_primary": "gpt-5.4-mini",
        "openai_fallback": "gpt-5.4-nano",
        "openai_reasoning_effort": "low",
        "openai_text_verbosity": "low",
    },
    LLMRole.EXTRACTION: {
        "provider": LLMProvider.ANTHROPIC,
        "anthropic_primary": "claude-3-5-haiku-20241022",
        "anthropic_fallback": "claude-3-5-haiku-20241022",
        "openai_primary": "gpt-5.4-mini",
        "openai_fallback": "gpt-5.4-nano",
        "openai_reasoning_effort": "low",
        "openai_text_verbosity": "low",
    },
}


# --- Pydantic models for role config ---------------------------------------


class OpenAIControls(BaseModel):
    """OpenAI-specific generation knobs (no-op for Anthropic providers)."""

    # Allowed values match the spec §8 sketch. Pydantic will reject anything else.
    reasoning_effort: Optional[str] = Field(
        default=None,
        description="One of: none, low, medium, high, xhigh",
    )
    text_verbosity: Optional[str] = Field(
        default=None,
        description="One of: low, medium, high",
    )
    store: bool = Field(default=False)

    @field_validator("reasoning_effort")
    @classmethod
    def _check_reasoning_effort(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        allowed = {"none", "low", "medium", "high", "xhigh"}
        if v not in allowed:
            raise ValueError(
                f"reasoning_effort must be one of {sorted(allowed)}, got {v!r}"
            )
        return v

    @field_validator("text_verbosity")
    @classmethod
    def _check_text_verbosity(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        allowed = {"low", "medium", "high"}
        if v not in allowed:
            raise ValueError(
                f"text_verbosity must be one of {sorted(allowed)}, got {v!r}"
            )
        return v


class LLMRoleConfig(BaseModel):
    """Per-role LLM configuration.

    A role's ``provider`` decides which client implementation backs it; the
    primary/fallback model strings are looked up against that provider's pricing
    table in ``config/pricing.yaml``.
    """

    provider: LLMProvider
    primary_model: str
    fallback_model: Optional[str] = None
    max_output_tokens: int = Field(default=4096, gt=0)
    temperature: float = Field(default=0.7, ge=0, le=1)
    openai: OpenAIControls = Field(default_factory=OpenAIControls)


# --- Helpers to build defaults from env --------------------------------------


def _bool_from_env(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _build_role_config_from_env(role: LLMRole) -> LLMRoleConfig:
    """Construct the default LLMRoleConfig for a role, honouring env overrides.

    Env vars (per spec §8):
      LLM_<ROLE>_PROVIDER=anthropic|openai
      LLM_<ROLE>_PRIMARY_MODEL=...
      LLM_<ROLE>_FALLBACK_MODEL=...
      LLM_<ROLE>_MAX_OUTPUT_TOKENS=int
      LLM_<ROLE>_REASONING_EFFORT=none|low|medium|high|xhigh
      LLM_<ROLE>_TEXT_VERBOSITY=low|medium|high
      LLM_<ROLE>_STORE=true|false
    """
    defaults = _ROLE_DEFAULTS[role]
    role_upper = role.value.upper()

    def _env(name: str) -> Optional[str]:
        """Read an env var, treating missing/empty/whitespace-only as unset.

        Centralised so every per-role env override falls back to the role
        default consistently — avoids the historical split where
        ``PRIMARY_MODEL=""`` fell back via truthiness but
        ``REASONING_EFFORT=""`` would crash the validator.
        """
        raw = os.getenv(name)
        if raw is None:
            return None
        stripped = raw.strip()
        return stripped or None

    provider_str = (_env(f"LLM_{role_upper}_PROVIDER") or "").lower()
    if provider_str:
        try:
            provider = LLMProvider(provider_str)
        except ValueError as exc:
            raise ValueError(
                f"Invalid LLM_{role_upper}_PROVIDER={provider_str!r}; "
                f"expected one of {[p.value for p in LLMProvider]}"
            ) from exc
    else:
        provider = defaults["provider"]

    if provider == LLMProvider.ANTHROPIC:
        primary_default = defaults["anthropic_primary"]
        fallback_default = defaults["anthropic_fallback"]
    else:
        primary_default = defaults["openai_primary"]
        fallback_default = defaults["openai_fallback"]

    primary_model = _env(f"LLM_{role_upper}_PRIMARY_MODEL") or primary_default
    fallback_model = _env(f"LLM_{role_upper}_FALLBACK_MODEL") or fallback_default

    max_tokens_env = _env(f"LLM_{role_upper}_MAX_OUTPUT_TOKENS")
    if max_tokens_env is None:
        max_output_tokens = 4096
    else:
        try:
            max_output_tokens = int(max_tokens_env)
        except ValueError as exc:
            raise ValueError(
                f"LLM_{role_upper}_MAX_OUTPUT_TOKENS must be a positive "
                f"integer, got: {max_tokens_env!r}"
            ) from exc

    openai_kwargs: dict = {}
    eff = _env(f"LLM_{role_upper}_REASONING_EFFORT")
    if eff is not None:
        openai_kwargs["reasoning_effort"] = eff
    elif provider == LLMProvider.OPENAI:
        openai_kwargs["reasoning_effort"] = defaults["openai_reasoning_effort"]
    verb = _env(f"LLM_{role_upper}_TEXT_VERBOSITY")
    if verb is not None:
        openai_kwargs["text_verbosity"] = verb
    elif provider == LLMProvider.OPENAI:
        openai_kwargs["text_verbosity"] = defaults["openai_text_verbosity"]
    store_env = _env(f"LLM_{role_upper}_STORE")
    if store_env is not None:
        openai_kwargs["store"] = _bool_from_env(store_env)

    return LLMRoleConfig(
        provider=provider,
        primary_model=primary_model,
        fallback_model=fallback_model,
        max_output_tokens=max_output_tokens,
        openai=OpenAIControls(**openai_kwargs),
    )


def _default_intake() -> LLMRoleConfig:
    return _build_role_config_from_env(LLMRole.INTAKE)


def _default_prediction() -> LLMRoleConfig:
    return _build_role_config_from_env(LLMRole.PREDICTION)


def _default_mediator() -> LLMRoleConfig:
    return _build_role_config_from_env(LLMRole.MEDIATOR)


def _default_extraction() -> LLMRoleConfig:
    return _build_role_config_from_env(LLMRole.EXTRACTION)


# --- Top-level config -------------------------------------------------------


class LLMConfig(BaseModel):
    """Configuration for LLM orchestrator components.

    Two layers coexist for back-compat:
    - **Flat fields** (``primary_model``, ``fallback_model``, ``max_tokens``,
      ``temperature``, ``anthropic_api_key``, ``openai_api_key``, etc.) — these
      are read directly by existing call sites and must be preserved until
      Task 5 of SHA-114 migrates them to the role-aware factory.
    - **Role-aware fields** (``intake``, ``prediction``, ``mediator``,
      ``extraction``) — populated from ``LLM_<ROLE>_*`` env vars, consumed by
      ``clients/factory.py``.

    Default behaviour (no env overrides) selects Anthropic for every role and
    matches the historical configuration exactly.
    """

    # API Keys
    anthropic_api_key: str = Field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", "")
    )
    openai_api_key: str = Field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", "")
    )

    # Supabase configuration
    supabase_url: str = Field(
        default_factory=lambda: os.getenv("SUPABASE_URL", "")
    )
    supabase_key: str = Field(
        default_factory=lambda: os.getenv("SUPABASE_KEY", "")
    )
    supabase_bucket: str = Field(default="evidence")

    # Model settings (legacy flat — kept for back-compat)
    primary_model: str = Field(default="claude-sonnet-4-20250514")
    fallback_model: str = Field(default="claude-3-5-haiku-20241022")
    max_tokens: int = Field(default=4096)
    temperature: float = Field(default=0.7, ge=0, le=1)

    # Intake settings
    max_conversation_turns: int = Field(default=50)
    min_completeness_for_prediction: float = Field(default=0.7, ge=0, le=1)

    # Prediction settings
    min_confidence_threshold: float = Field(default=0.5, ge=0, le=1)
    cite_or_abstain: bool = Field(default=True)

    # Paths
    data_dir: Path = Field(default=Path("./data"))
    sessions_dir: Path = Field(default=Path("./data/sessions"))
    predictions_dir: Path = Field(default=Path("./data/predictions"))

    # Per-role LLM config (SHA-114). Defaults are constructed from env at
    # instantiation time so each `LLMConfig()` reflects the current
    # `LLM_<ROLE>_*` env state.
    intake: LLMRoleConfig = Field(default_factory=_default_intake)
    prediction: LLMRoleConfig = Field(default_factory=_default_prediction)
    mediator: LLMRoleConfig = Field(default_factory=_default_mediator)
    extraction: LLMRoleConfig = Field(default_factory=_default_extraction)

    @field_validator("anthropic_api_key")
    @classmethod
    def validate_anthropic_key(cls, v: str) -> str:
        """Warn if API key is not set (legacy soft check, kept for back-compat)."""
        if not v:
            import warnings
            warnings.warn("ANTHROPIC_API_KEY not set. LLM calls will fail.")
        return v

    @model_validator(mode="after")
    def _require_keys_for_selected_providers(self) -> "LLMConfig":
        """Conditional API-key validation per spec §3.8.

        Hard-fail only if a role explicitly opts into a provider whose key is
        missing AND that opt-in came from an env override (not the silent
        default). The legacy flat-field warn-only behaviour for missing
        ``ANTHROPIC_API_KEY`` under default config is preserved by
        ``validate_anthropic_key`` above.
        """
        roles = (self.intake, self.prediction, self.mediator, self.extraction)
        used_providers = {r.provider for r in roles}

        # OpenAI is never the silent default for any role today, so any
        # OpenAI-using role implies an explicit env opt-in. Require the key.
        if LLMProvider.OPENAI in used_providers and not self.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY required by selected LLM role "
                f"(roles using openai: "
                f"{[r for r, cfg in self._roles().items() if cfg.provider == LLMProvider.OPENAI]})"
            )

        # For Anthropic we keep the warn-only default behaviour so unconfigured
        # dev environments still construct successfully (matches pre-SHA-114).
        return self

    def _roles(self) -> dict[LLMRole, LLMRoleConfig]:
        return {
            LLMRole.INTAKE: self.intake,
            LLMRole.PREDICTION: self.prediction,
            LLMRole.MEDIATOR: self.mediator,
            LLMRole.EXTRACTION: self.extraction,
        }

    def role_config(self, role: LLMRole) -> LLMRoleConfig:
        """Return the LLMRoleConfig for the given role."""
        return self._roles()[role]

    def ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.predictions_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Create configuration from environment variables."""
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            supabase_url=os.getenv("SUPABASE_URL", ""),
            supabase_key=os.getenv("SUPABASE_KEY", ""),
        )

    model_config = {"arbitrary_types_allowed": True}
