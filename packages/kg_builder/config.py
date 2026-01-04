"""
Configuration for the Knowledge Graph Builder package.
"""

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class KGConfig(BaseModel):
    """Configuration for Knowledge Graph builder components."""

    # Storage settings
    storage_backend: str = Field(default="json")  # json or neo4j
    data_dir: Path = Field(default=Path("./data/knowledge_graphs"))

    # Neo4j settings (for future migration)
    neo4j_uri: str = Field(
        default_factory=lambda: os.getenv("NEO4J_URI", "bolt://localhost:7687")
    )
    neo4j_user: str = Field(
        default_factory=lambda: os.getenv("NEO4J_USER", "neo4j")
    )
    neo4j_password: str = Field(
        default_factory=lambda: os.getenv("NEO4J_PASSWORD", "")
    )

    # Validation settings
    strict_validation: bool = Field(default=True)
    min_confidence_threshold: float = Field(default=0.5, ge=0, le=1)

    # Extraction settings
    extract_temporal_relations: bool = Field(default=True)
    extract_evidence_relations: bool = Field(default=True)

    def ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "KGConfig":
        """Create configuration from environment variables."""
        return cls()

    model_config = {"arbitrary_types_allowed": True}
