from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import current_user
from app.db import Base, get_db
from app.models import Alert, AuditLog, Entity, Investigation, User
from app.routes.core import router


def test_core_aggregate_and_search_endpoints_are_investigation_scoped():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        actor = User(email="scope-audit@example.org", password_hash="test", role="analyst")
        other = User(email="scope-private@example.org", password_hash="test", role="analyst")
        db.add_all([actor, other])
        db.flush()
        visible = Investigation(title="Visible", owner_id=actor.id)
        private = Investigation(title="Private", owner_id=other.id)
        db.add_all([visible, private])
        db.flush()
        db.add_all(
            [
                Entity(
                    investigation_id=visible.id,
                    type="domain",
                    canonical_value="visible.example",
                    label="visible",
                ),
                Entity(
                    investigation_id=private.id,
                    type="domain",
                    canonical_value="private.example",
                    label="private",
                ),
                Alert(
                    investigation_id=visible.id,
                    event_type="test",
                    title="visible alert",
                    dedupe_key="visible-alert",
                ),
                Alert(
                    investigation_id=private.id,
                    event_type="test",
                    title="private alert",
                    dedupe_key="private-alert",
                ),
                AuditLog(
                    user_id=actor.id,
                    investigation_id=visible.id,
                    action="visible.action",
                    object_type="test",
                ),
                AuditLog(
                    user_id=other.id,
                    investigation_id=private.id,
                    action="private.action",
                    object_type="test",
                ),
            ]
        )
        db.commit()

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    def database():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[current_user] = lambda: actor
    with TestClient(app) as client:
        dashboard = client.get("/api/v1/dashboard").json()
        assert dashboard["investigations"] == 1
        assert dashboard["entities"] == 1
        assert dashboard["alerts"] == 1
        assert [item["title"] for item in client.get("/api/v1/investigations").json()["items"]] == ["Visible"]
        assert [item["title"] for item in client.get("/api/v1/alerts").json()["items"]] == ["visible alert"]
        assert client.get("/api/v1/audit").json()["total"] == 1
        search = client.get("/api/v1/search", params={"q": "private"}).json()
        assert search == {"entities": [], "observations": [], "threat_indicators": []}
        assert client.get("/api/v1/admin/connectors").status_code == 403

    engine.dispose()
