"""
API configuration and settings.
"""

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


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

    # Data paths
    data_dir: Path = Field(default=Path("./data"))
    sessions_dir: Path = Field(default=Path("./data/sessions"))
    kg_dir: Path = Field(default=Path("./data/knowledge_graphs"))

    # CORS
    cors_origins: list = Field(default=["http://localhost:3000", "http://localhost:8000"])

    def ensure_directories(self) -> None:
        """Create necessary directories."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.kg_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "APIConfig":
        """Create configuration from environment variables."""
        return cls(
            debug=os.getenv("DEBUG", "false").lower() == "true",
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8000")),
        )

    model_config = {"arbitrary_types_allowed": True}


# Global config instance
config = APIConfig.from_env()
