"""
Shared pytest fixtures: an isolated in-memory SQLite DB per test run,
with the FastAPI app's get_db dependency overridden to use it — so
tests never touch the real backend/medbox.db file.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import models
from backend.database import get_db
from backend.main import app


@pytest.fixture()
def client():
    # StaticPool: a plain in-memory SQLite DB is per-connection, so
    # without pinning to one shared connection each new Session would
    # see an empty, disconnected database.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)

    def _override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
