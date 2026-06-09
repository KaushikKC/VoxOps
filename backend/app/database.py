"""Database engine, session management and ORM base.

Uses SQLAlchemy 2.0 with a SQLite default. The session factory is exposed as a
FastAPI dependency (:func:`get_db`) and the schema is created on startup via
:func:`init_db`.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()


def _ensure_sqlite_dir(url: str) -> None:
    """Create the parent directory for a SQLite file URL if needed."""
    prefix = "sqlite:///"
    if url.startswith(prefix):
        db_path = url[len(prefix) :]
        if db_path and db_path != ":memory:":
            Path(db_path).resolve().parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_dir(settings.database_url)

# SQLite needs ``check_same_thread=False`` to be used across FastAPI's threads.
_connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. Imports models for side effects of registration."""
    # Import here to avoid circular imports and ensure models are registered.
    from app import models  # noqa: F401

    os.makedirs(os.path.dirname(__file__), exist_ok=True)
    Base.metadata.create_all(bind=engine)
