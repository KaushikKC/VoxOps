"""Pytest fixtures.

Configures an isolated temp SQLite database and disables signature verification
*before* the app is imported, then provides a TestClient with a freshly created
schema per test.
"""

from __future__ import annotations

import os
import tempfile

# Must be set before any app module (which binds the engine at import) is loaded.
_tmp = tempfile.mkdtemp(prefix="vao-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["ELEVENLABS_VERIFY_SIGNATURE"] = "false"
os.environ["ELEVENLABS_WEBHOOK_SECRET"] = "test-secret"
os.environ["CHROMA_PERSIST_DIR"] = f"{_tmp}/chroma"
os.environ["ANTHROPIC_API_KEY"] = ""  # force offline analyzer

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_schema():
    """Recreate all tables before each test for isolation."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
