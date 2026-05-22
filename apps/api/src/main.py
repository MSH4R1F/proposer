"""
FastAPI application entry point.

Legal Mediation System API
"""

import sys
from pathlib import Path

# Add packages and project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))  # Add project root for apps.* imports
sys.path.insert(0, str(project_root / "packages"))

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
import structlog

from apps.api.src.config import APIConfig, config
from apps.api.src.db.engine import create_engine_from_url, make_sessionmaker
from apps.api.src.routers import chat, evidence, predictions, cases, disputes, mediation, domains

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(colors=True),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


def create_lifespan(settings: APIConfig):
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Application lifespan handler."""
        logger.info("api_starting", host=settings.host, port=settings.port)
        logger.debug(
            "environment_check",
            anthropic_key_set=bool(settings.anthropic_api_key),
            openai_key_set=bool(settings.openai_api_key),
            supabase_url_set=bool(settings.supabase_url),
        )

        logger.debug(
            "ensuring_directories",
            data_dir=str(settings.data_dir),
            sessions_dir=str(settings.sessions_dir),
            kg_dir=str(settings.kg_dir),
        )
        settings.ensure_directories()
        logger.debug("directories_ready")

        engine = create_engine_from_url(settings.database_url)
        app.state.db_engine = engine
        app.state.db_sessionmaker = make_sessionmaker(engine)
        app.state.settings = settings

        try:
            yield
        finally:
            await engine.dispose()
            logger.info("api_shutting_down")

    return lifespan


def create_app(settings: Optional[APIConfig] = None) -> FastAPI:
    """Application factory.

    Keeps construction side-effect-free so tests can build an app with a
    custom ``APIConfig`` (e.g. ``debug=True``/``False``). The dev router is
    mounted lazily and only when ``settings.debug`` is true, so production
    paths don't import the agent-loop dependencies at module load time.
    """
    settings = settings or config

    app = FastAPI(
        title="Legal Mediation System API",
        description="""
        AI-powered mediation platform for UK tenancy deposit disputes.

        Features:
        - Conversational intake agent
        - Knowledge graph construction
        - Outcome prediction with reasoning traces
        - Evidence management
        """,
        version="0.1.0",
        lifespan=create_lifespan(settings),
    )

    # Add CORS middleware
    logger.debug("configuring_cors", allowed_origins=settings.cors_origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    logger.debug(
        "registering_routers",
        routers=["chat", "evidence", "predictions", "cases", "disputes", "mediation", "domains"],
    )
    app.include_router(chat.router)
    app.include_router(evidence.router)
    app.include_router(predictions.router)
    app.include_router(cases.router)
    app.include_router(disputes.router)
    app.include_router(mediation.router)
    app.include_router(domains.router)
    logger.debug("routers_registered")

    if settings.debug:
        # Import lazily so production paths don't pull in the agent-loop
        # dependencies (ClaudeClient, etc.) at module-load time.
        from .routers import dev

        app.include_router(dev.router)
        logger.info("dev_router_registered")

    @app.get("/")
    async def root():
        """Root endpoint."""
        logger.debug("root_endpoint_accessed")
        return {
            "name": "Legal Mediation System API",
            "version": "0.1.0",
            "status": "running",
            "docs": "/docs",
        }

    @app.get("/health")
    async def health_check():
        """Liveness check: process is up."""
        health_status = {
            "status": "healthy",
            "anthropic_configured": bool(settings.anthropic_api_key),
            "openai_configured": bool(settings.openai_api_key),
            "supabase_configured": bool(settings.supabase_url),
        }
        logger.debug("health_check", **health_status)
        return health_status

    @app.get("/readyz")
    async def readiness_check():
        """Readiness check: process can reach a migrated database."""
        try:
            async with app.state.db_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                version = await conn.scalar(text("SELECT version_num FROM alembic_version"))
        except Exception as exc:
            logger.warning("readiness_check_failed", error_type=type(exc).__name__)
            raise HTTPException(status_code=503, detail="database_not_ready") from exc
        return {"status": "ready", "alembic_version": version}

    return app


# Module-level app for `uvicorn main:app` and existing test imports.
app = create_app(config)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=config.host,
        port=config.port,
        reload=config.debug,
    )
