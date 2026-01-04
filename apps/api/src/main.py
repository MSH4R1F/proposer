"""
FastAPI application entry point.

Legal Mediation System API
"""

import sys
from pathlib import Path

# Add packages to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "packages"))

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from .config import config
from .routers import chat, evidence, predictions, cases

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
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
    config.ensure_directories()

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
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(chat.router)
app.include_router(evidence.router)
app.include_router(predictions.router)
app.include_router(cases.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Legal Mediation System API",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "anthropic_configured": bool(config.anthropic_api_key),
        "openai_configured": bool(config.openai_api_key),
        "supabase_configured": bool(config.supabase_url),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=config.host,
        port=config.port,
        reload=config.debug,
    )
