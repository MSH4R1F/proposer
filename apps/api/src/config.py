"""
API configuration and settings.
"""

import os
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, Field, model_validator
import structlog

logger = structlog.get_logger()


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
    cors_origins: list = Field(default=["http://localhost:3000", "http://localhost:8000"])

    # Environment + Database
    app_env: str = Field(default_factory=lambda: os.getenv("APP_ENV", "local"))
    database_url: str = Field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://proposer:proposer-dev@localhost:5432/proposer",
        )
    )

    @model_validator(mode="after")
    def validate_database_url_for_environment(self) -> "APIConfig":
        if self.app_env != "production":
            return self
        raw = os.getenv("DATABASE_URL")
        if not raw:
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
