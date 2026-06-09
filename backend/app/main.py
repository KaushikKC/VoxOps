"""FastAPI application entrypoint.

Wires configuration, database initialization, CORS and the API routers. Run with::

    uvicorn app.main:app --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import get_settings
from app.database import init_db

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("observability")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database (%s)", settings.database_url)
    init_db()
    logger.info(
        "Sentiment analyzer: %s",
        "claude" if settings.use_claude_sentiment else "offline-deterministic",
    )
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="Voice Agent Observability Dashboard",
    description=(
        "Observability for ElevenLabs conversational voice agents: per-turn "
        "latency, interruptions, sentiment, task completion, cost and replay/audit."
    ),
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Liveness probe."""
    return {
        "status": "ok",
        "version": __version__,
        "env": settings.app_env,
        "sentiment": "claude" if settings.use_claude_sentiment else "offline",
    }


# API routers are registered as they are implemented (see app/routers/).
