"""
Configuration for the LLM Orchestrator package.

Manages API keys, model settings, and runtime configuration.
"""

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class LLMConfig(BaseModel):
    """Configuration for LLM orchestrator components."""

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

    # Model settings
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

    @field_validator("anthropic_api_key")
    @classmethod
    def validate_anthropic_key(cls, v: str) -> str:
        """Warn if API key is not set."""
        if not v:
            import warnings
            warnings.warn("ANTHROPIC_API_KEY not set. LLM calls will fail.")
        return v

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
