"""Shared isolated SQLite fixtures; records are explicit test data only."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker

from app.auth import current_user
from app.db import Base, get_db
from app.models import Investigation, User
from app.routes.collection import router as collection_router


@pytest.fixture(scope="session")
def engine(tmp_path_factory):
    from sqlalchemy import create_engine

    path = tmp_path_factory.mktemp("database") / "test.sqlite"
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine):
    factory = sessionmaker(engine, expire_on_commit=False)
    session = factory()
    yield session
    session.rollback()
    session.close()
    # Tests use one in-memory schema; clear rows between tests in FK-safe order.
    for table in reversed(Base.metadata.sorted_tables):
        with engine.begin() as connection:
            connection.execute(table.delete())


@pytest.fixture
def user(db):
    record = User(email="fixture@example.org", password_hash="test fixture hash", role="analyst")
    db.add(record)
    db.flush()
    return record


@pytest.fixture
def investigation(db, user):
    record = Investigation(title="Explicit test investigation", objective="test", owner_id=user.id)
    db.add(record)
    db.flush()
    return record


@pytest.fixture
def client(db, user):
    app = FastAPI()
    app.include_router(collection_router, prefix="/api/v1")
    factory = sessionmaker(db.get_bind(), expire_on_commit=False)

    def database():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[current_user] = lambda: user
    with TestClient(app) as test_client:
        yield test_client
