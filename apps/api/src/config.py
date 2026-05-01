"""
API configuration and settings.
"""

import os
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, Field, field_validator, model_validator
import structlog

logger = structlog.get_logger()

_ALLOWED_RETRIEVAL_STRATEGIES = {
    "chunk_rag",
    "proposition_direct",
    "proposition_pagerank",
    "hybrid_chunk_proposition",
}


class APIConfig(BaseModel):
    """Configuration for the API server."""

    # Server settings
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    debug: bool = Field(default=False)

    # API Keys
    anthropic_api_key: str = Field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", "")
    )
    openai_api_key: str = Field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", "")
    )

    # Supabase
    supabase_url: str = Field(
        default_factory=lambda: os.getenv("SUPABASE_URL", "")
    )
    supabase_key: str = Field(
        default_factory=lambda: os.getenv("SUPABASE_KEY", "")
    )
    supabase_bucket: str = Field(default="evidence")

    # Langfuse (observability) - all three required to enable export
    langfuse_public_key: str = Field(
        default_factory=lambda: os.getenv("LANGFUSE_PUBLIC_KEY", "")
    )
    langfuse_secret_key: str = Field(
        default_factory=lambda: os.getenv("LANGFUSE_SECRET_KEY", "")
    )
    langfuse_host: str = Field(
        default_factory=lambda: os.getenv("LANGFUSE_HOST", "")
    )

    # Data paths
    data_dir: Path = Field(default=Path("./data"))
    sessions_dir: Path = Field(default=Path("./data/sessions"))
    kg_dir: Path = Field(default=Path("./data/knowledge_graphs"))

    # CORS
    cors_origins: list = Field(
        default_factory=lambda: (
            [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
            or [
                "http://localhost:3000",
                "http://localhost:3001",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:3001",
                "http://localhost:8000",
                "http://127.0.0.1:8000",
            ]
        )
    )

    # Prediction mode (SHA-33 ablation seam — consumed by SHA-32 harness)
    # Valid values: rag_only / kg_only / hybrid / llm_only
    prediction_mode: str = Field(
        default_factory=lambda: os.getenv("PREDICTION_MODE", "hybrid").lower()
    )
    # Retrieval strategy (SHA-36 Phase 2). Valid values:
    # chunk_rag / proposition_direct / proposition_pagerank /
    # hybrid_chunk_proposition. Defaults to current production behaviour.
    retrieval_strategy: str = Field(
        default_factory=lambda: os.getenv(
            "RETRIEVAL_STRATEGY", "chunk_rag"
        ).lower(),
        validate_default=True,
    )

    # Environment + Database
    app_env: str = Field(default_factory=lambda: os.getenv("APP_ENV", "local"))
    database_url: str = Field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://proposer:proposer-dev@localhost:5432/proposer",
        )
    )

    @field_validator("retrieval_strategy")
    @classmethod
    def validate_retrieval_strategy(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in _ALLOWED_RETRIEVAL_STRATEGIES:
            allowed = ", ".join(sorted(_ALLOWED_RETRIEVAL_STRATEGIES))
            raise ValueError(
                f"retrieval_strategy must be one of: {allowed}; got {value!r}"
            )
        return normalized

    @model_validator(mode="after")
    def validate_database_url_for_environment(self) -> "APIConfig":
        if self.app_env != "production":
            return self
        if self.debug:
            raise ValueError("DEBUG must be false in production")
        raw = os.getenv("DATABASE_URL") or self.database_url
        if (
            not os.getenv("DATABASE_URL")
            and raw == "postgresql+asyncpg://proposer:proposer-dev@localhost:5432/proposer"
        ):
            raise ValueError("DATABASE_URL is required in production")
        host = (urlparse(raw).hostname or "").lower()
        if host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"} or "proposer-dev" in raw:
            raise ValueError("production must not use the local dev database")
        qs = parse_qs(urlparse(raw).query)
        sslmode = (qs.get("sslmode") or [""])[0]
        if sslmode not in {"require", "verify-ca", "verify-full"}:
            raise ValueError("production DATABASE_URL must set sslmode=require or stronger")
        return self

    @property
    def langfuse_configured(self) -> bool:
        """True when all three LangFuse credentials are set."""
        return bool(
            self.langfuse_public_key
            and self.langfuse_secret_key
            and self.langfuse_host
        )

    def ensure_directories(self) -> None:
        """Create necessary directories."""
        logger.debug("creating_directories",
                     data_dir=str(self.data_dir),
                     sessions_dir=str(self.sessions_dir),
                     kg_dir=str(self.kg_dir))
        
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.kg_dir.mkdir(parents=True, exist_ok=True)
        
        logger.debug("directories_created")

    @classmethod
    def from_env(cls) -> "APIConfig":
        """Create configuration from environment variables."""
        debug_mode = os.getenv("DEBUG", "false").lower() == "true"
        host = os.getenv("HOST", "0.0.0.0")
        port = int(os.getenv("PORT", "8000"))
        
        logger.debug("loading_config_from_env",
                     debug=debug_mode,
                     host=host,
                     port=port,
                     has_anthropic_key=bool(os.getenv("ANTHROPIC_API_KEY")),
                     has_openai_key=bool(os.getenv("OPENAI_API_KEY")),
                     has_supabase_url=bool(os.getenv("SUPABASE_URL")))
        
        return cls(
            debug=debug_mode,
            host=host,
            port=port,
        )

    model_config = {"arbitrary_types_allowed": True}


# Global config instance
config = APIConfig.from_env()
