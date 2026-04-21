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
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from apps.api.src.config import APIConfig, config
from apps.api.src.routers import chat, evidence, predictions, cases, disputes, mediation

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("api_starting", host=config.host, port=config.port)
    logger.debug("environment_check", 
                 anthropic_key_set=bool(config.anthropic_api_key),
                 openai_key_set=bool(config.openai_api_key),
                 supabase_url_set=bool(config.supabase_url))
    
    logger.debug("ensuring_directories", 
                 data_dir=str(config.data_dir),
                 sessions_dir=str(config.sessions_dir),
                 kg_dir=str(config.kg_dir))
    config.ensure_directories()
    logger.debug("directories_ready")

    yield

    # Shutdown
    logger.info("api_shutting_down")


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
        lifespan=lifespan,
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
        routers=["chat", "evidence", "predictions", "cases", "disputes", "mediation"],
    )
    app.include_router(chat.router)
    app.include_router(evidence.router)
    app.include_router(predictions.router)
    app.include_router(cases.router)
    app.include_router(disputes.router)
    app.include_router(mediation.router)
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
        """Health check endpoint."""
        health_status = {
            "status": "healthy",
            "anthropic_configured": bool(settings.anthropic_api_key),
            "openai_configured": bool(settings.openai_api_key),
            "supabase_configured": bool(settings.supabase_url),
        }
        logger.debug("health_check", **health_status)
        return health_status

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
