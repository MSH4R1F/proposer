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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from apps.api.src.config import config
from apps.api.src.routers import chat, evidence, predictions, cases, disputes

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


# Create FastAPI app
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
logger.debug("configuring_cors", allowed_origins=config.cors_origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
logger.debug("registering_routers", routers=["chat", "evidence", "predictions", "cases", "disputes"])
app.include_router(chat.router)
app.include_router(evidence.router)
app.include_router(predictions.router)
app.include_router(cases.router)
app.include_router(disputes.router)
logger.debug("routers_registered")


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
        "anthropic_configured": bool(config.anthropic_api_key),
        "openai_configured": bool(config.openai_api_key),
        "supabase_configured": bool(config.supabase_url),
    }
    logger.debug("health_check", **health_status)
    return health_status


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=config.host,
        port=config.port,
        reload=config.debug,
    )
