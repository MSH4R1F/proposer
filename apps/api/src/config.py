"""
API configuration and settings.
"""

import os
from pathlib import Path
from typing import List, Optional
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, Field, model_validator
import structlog

logger = structlog.get_logger()


def _parse_csv_env(value: str) -> List[str]:
    """Parse a comma-separated env value with whitespace tolerance + dedupe.

    Returns the entries in the order they first appear. Empty entries
    (created by trailing/leading commas or blank fields) are dropped.
    """
    if not value:
        return []
    seen: set[str] = set()
    out: List[str] = []
    for raw in value.split(","):
        item = raw.strip()
        if not item:
            continue
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


_DEFAULT_DOMAIN = "housing.deposit.v1"


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

    # SHA-20 Phase 3: Multi-domain runtime flags
    # ---------------------------------------------------------------
    # `enabled_domains`: domain ids permitted to run as the default routed
    #   domain. Comma-separated env: ENABLED_DOMAINS. Phase 3 only enables
    #   `housing.deposit.v1`; other domains return "domain unavailable" until
    #   their launch gate is signed (Phase 8).
    # `default_domain`: domain used when a request omits `domain_id`.
    # `domain_router_enabled`: future toggle for router-based domain
    #   selection (Phase 6+); Phase 3 defaults to False.
    # `domain_cross_retrieval_allowed`: future toggle for cross-namespace
    #   retrieval; default False until Phase 4.
    # `domain_beta_allowlist_user_ids`: stable user IDs (Supabase UUIDs once
    #   auth is enabled) permitted to run beta-stage domains. Comma-separated.
    # `domain_employment_beta_allowlist_user_ids`: family-specific beta
    #   allowlist for employment.* research domains.
    # `domain_strict_eval_gates`: Phase 8 fail-closed launch gate enforcement
    #   toggle. Phase 3 leaves it on; gate enforcement itself is partial.
    # `domain_gate_artifact_dir`: directory holding signed launch-gate
    #   artifacts (resolved by Phase 8 / SHA-122).
    enabled_domains: List[str] = Field(
        default_factory=lambda: _parse_csv_env(
            os.getenv("ENABLED_DOMAINS", _DEFAULT_DOMAIN)
        )
    )
    default_domain: str = Field(
        default_factory=lambda: os.getenv("DEFAULT_DOMAIN", _DEFAULT_DOMAIN)
    )
    domain_router_enabled: bool = Field(
        default_factory=lambda: os.getenv("DOMAIN_ROUTER_ENABLED", "false").lower()
        == "true"
    )
    domain_cross_retrieval_allowed: bool = Field(
        default_factory=lambda: os.getenv(
            "DOMAIN_CROSS_RETRIEVAL_ALLOWED", "false"
        ).lower()
        == "true"
    )
    domain_beta_allowlist_user_ids: List[str] = Field(
        default_factory=lambda: _parse_csv_env(
            os.getenv("DOMAIN_BETA_ALLOWLIST_USER_IDS", "")
        )
    )
    domain_employment_beta_allowlist_user_ids: List[str] = Field(
        default_factory=lambda: _parse_csv_env(
            os.getenv("DOMAIN_EMPLOYMENT_BETA_ALLOWLIST_USER_IDS", "")
        )
    )
    domain_strict_eval_gates: bool = Field(
        default_factory=lambda: os.getenv("DOMAIN_STRICT_EVAL_GATES", "true").lower()
        == "true"
    )
    domain_gate_artifact_dir: Path = Field(
        default_factory=lambda: Path(
            os.getenv(
                "DOMAIN_GATE_ARTIFACT_DIR", "data/eval_artifacts/domain_gates"
            )
        )
    )

    # Environment + Database
    app_env: str = Field(default_factory=lambda: os.getenv("APP_ENV", "local"))
    database_url: str = Field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://proposer:proposer-dev@localhost:5432/proposer",
        )
    )

    @model_validator(mode="after")
    def validate_domain_settings(self) -> "APIConfig":
        """Reject unknown domain ids in ENABLED_DOMAINS / DEFAULT_DOMAIN at startup.

        Validation defers to ``domain_core``'s registry; if registry loading
        itself fails (e.g. corrupt YAML) we surface that as a config error too.
        """
        try:
            from domain_core import list_domain_specs  # type: ignore

            registered = {str(s.id) for s in list_domain_specs()}
        except Exception as exc:  # pragma: no cover - registry failure is config error
            raise ValueError(
                f"Failed to load domain registry while validating config: {exc}"
            ) from exc

        # default_domain must be a known id.
        if self.default_domain not in registered:
            raise ValueError(
                f"DEFAULT_DOMAIN={self.default_domain!r} is not a registered "
                f"domain id. Registered: {sorted(registered)}"
            )

        # default_domain must be in enabled_domains (otherwise no routing works).
        if self.default_domain not in self.enabled_domains:
            raise ValueError(
                f"DEFAULT_DOMAIN={self.default_domain!r} must be present in "
                f"ENABLED_DOMAINS={self.enabled_domains!r}"
            )

        # every entry in enabled_domains must be a known id.
        unknown = [d for d in self.enabled_domains if d not in registered]
        if unknown:
            raise ValueError(
                f"ENABLED_DOMAINS contains unknown domain id(s) {unknown!r}. "
                f"Registered: {sorted(registered)}"
            )
        return self

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
