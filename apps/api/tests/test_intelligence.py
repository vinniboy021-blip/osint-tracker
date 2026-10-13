import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import current_user
from app.config import settings
from app.db import Base, get_db
from app.intelligence import normalize_identifier, validate_indicator
from app.models import (
    AuditLog,
    CorrelationCandidate,
    CorrelationReview,
    Entity,
    EntityRelationship,
    Evidence,
    Investigation,
    InvestigationMember,
    User,
)
from app.reporting import csv_export
from app.routes.intelligence import router


@pytest.fixture
def domain_api(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        analyst = User(email="domain-test@example.org", password_hash="test-only", role="analyst")
        other = User(email="other-test@example.org", password_hash="test-only", role="analyst")
        viewer = User(email="viewer-test@example.org", password_hash="test-only", role="viewer")
        db.add_all([analyst, other, viewer])
        db.flush()
        workspace = Investigation(title="Fixture: authorized investigation", owner_id=analyst.id)
        private = Investigation(title="Fixture: separate investigation", owner_id=other.id)
        db.add_all([workspace, private])
        db.flush()
        db.add(InvestigationMember(investigation_id=workspace.id, user_id=viewer.id, role="viewer"))
        db.commit()
    app = FastAPI()
    app.include_router(router)
    actor = {"user": analyst}

    def database():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[current_user] = lambda: actor["user"]
    monkeypatch.setattr(settings, "evidence_path", tmp_path)
    with TestClient(app) as client:
        yield client, factory, workspace.id, private.id, actor, viewer
    engine.dispose()


def test_investigation_isolation_and_readonly_permissions(domain_api):
    client, _factory, workspace, private, actor, viewer = domain_api
    for route in ("evidence", "reports", "correlations", "graph", "ai/runs", "threat-indicators"):
        assert client.get(f"/{route}", params={"investigation_id": private}).status_code in {403, 404}
    actor["user"] = viewer
    assert client.get("/evidence", params={"investigation_id": workspace}).status_code == 200
    assert (
        client.post("/reports", json={"investigation_id": workspace, "title": "forbidden"}).status_code == 403
    )
    assert (
        client.post(
            "/evidence", data={"investigation_id": workspace}, files={"file": ("source.txt", b"source")}
        ).status_code
        == 403
    )


def test_evidence_versions_verification_download_and_audited_purge(domain_api):
    client, factory, workspace, _private, _actor, _viewer = domain_api
    response = client.post(
        "/evidence",
        data={"investigation_id": workspace, "source_url": "https://example.org", "retention_days": "10"},
        files={"file": ("../../proof.html", b"<script>untrusted</script>", "text/html")},
    )
    assert response.status_code == 201, response.text
    evidence = response.json()
    assert evidence["filename"] == "proof.html" and "storage_key" not in evidence
    evidence_id = evidence["id"]
    download = client.get(f"/evidence/{evidence_id}/download")
    assert download.content == b"<script>untrusted</script>"
    assert download.headers["content-type"] == "application/octet-stream"
    assert download.headers["x-content-type-options"] == "nosniff"
    assert client.post(f"/evidence/{evidence_id}/verify").json()["valid"]
    version = client.post(
        f"/evidence/{evidence_id}/versions", files={"file": ("proof.txt", b"second version")}
    )
    assert version.status_code == 201 and version.json()["version"] == 2
    assert (
        client.get(f"/evidence/{evidence_id}/download", params={"version": 1}).content
        == b"<script>untrusted</script>"
    )
    assert client.get(f"/evidence/{evidence_id}/download").content == b"second version"
    assert client.delete(f"/evidence/{evidence_id}").json()["audit_preserved"]
    assert client.get(f"/evidence/{evidence_id}/download").status_code == 404
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Evidence)) == 0
        assert (
            db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "evidence.purged"))
            == 1
        )


def test_entity_and_evidence_cross_investigation_ids_are_rejected(domain_api):
    client, factory, workspace, private, _actor, _viewer = domain_api
    with factory() as db:
        entity = Entity(
            investigation_id=private, type="domain", canonical_value="private.example", label="private"
        )
        db.add(entity)
        db.commit()
        entity_id = entity.id
    result = client.post(
        "/evidence",
        data={"investigation_id": workspace, "entity_id": entity_id},
        files={"file": ("proof.txt", b"source")},
    )
    assert result.status_code == 422
    assert (
        client.get(
            "/graph/path", params={"investigation_id": workspace, "source": entity_id, "target": entity_id}
        ).status_code
        == 404
    )


def test_review_confirm_revoke_and_graph_use_actual_persisted_relationships(domain_api):
    client, factory, workspace, private, _actor, _viewer = domain_api
    with factory() as db:
        a = Entity(
            investigation_id=workspace,
            type="organization",
            canonical_value="Example Corporation A",
            label="A",
        )
        b = Entity(
            investigation_id=workspace,
            type="organization",
            canonical_value="Example Corporation B",
            label="B",
        )
        outsider = Entity(
            investigation_id=private,
            type="organization",
            canonical_value="Example Corporation C",
            label="private",
        )
        db.add_all([a, b, outsider])
        db.commit()
        aid, bid = a.id, b.id
    suggested = client.post("/correlations/suggest", json={"investigation_id": workspace})
    assert suggested.status_code == 200 and suggested.json()["total"] == 1
    candidate_id = suggested.json()["items"][0]["id"]
    assert client.post("/correlations/suggest", json={"investigation_id": workspace}).json()["total"] == 0
    assert client.get("/graph", params={"investigation_id": workspace}).json()["edges"] == []
    assert (
        client.post(f"/correlations/{candidate_id}/review", json={"decision": "confirmed"}).status_code == 422
    )
    review = client.post(
        f"/correlations/{candidate_id}/review",
        json={"decision": "confirmed", "notes": "Fixture manual review; distinct entities remain distinct"},
    )
    assert review.status_code == 200, review.text
    graph = client.get("/graph", params={"investigation_id": workspace}).json()
    assert len(graph["nodes"]) == 2 and len(graph["edges"]) == 1
    assert graph["edges"][0]["data"]["status"] == "confirmed"
    assert client.get(
        "/graph/path", params={"investigation_id": workspace, "source": aid, "target": bid}
    ).json()["path"] == [aid, bid]
    assert (
        client.post(
            f"/correlations/{candidate_id}/review", json={"decision": "rejected", "notes": "revoked"}
        ).status_code
        == 200
    )
    assert client.get("/graph", params={"investigation_id": workspace}).json()["edges"] == []
    assert (
        client.get(
            "/graph/path", params={"investigation_id": workspace, "source": aid, "target": bid}
        ).json()["path"]
        == []
    )
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(CorrelationReview)) == 2
        assert db.scalar(select(func.count()).select_from(EntityRelationship)) == 1
        assert db.get(CorrelationCandidate, candidate_id).status == "rejected"


def test_reports_and_ai_use_only_real_persisted_metadata(domain_api):
    client, _factory, workspace, _private, _actor, _viewer = domain_api
    upload = client.post(
        "/evidence",
        data={"investigation_id": workspace, "source_url": "https://example.org/public"},
        files={"file": ("fixture.txt", b"explicitly identified test data")},
    ).json()
    report = client.post(
        "/reports", json={"investigation_id": workspace, "title": "Test fixture export", "format": "json"}
    )
    assert report.status_code == 201
    exported = client.get(f"/reports/{report.json()['id']}/download").json()
    assert exported["evidence"][0]["id"] == upload["id"]
    assert exported["evidence"][0]["source_url"] == "https://example.org/public"
    assert "storage_key" not in exported["evidence"][0]
    assert exported["observations"] == []
    ai = client.post("/ai/analyze", json={"investigation_id": workspace, "task": "summary"})
    assert ai.status_code == 201, ai.text
    response = ai.json()["response"]
    assert response["citations"][0]["id"] == f"evidence:{upload['id']}"
    assert response["hypotheses"] == [] and response["inferences"] == []


def test_indicators_validated_idempotent_and_exported_with_provenance(domain_api):
    client, _factory, workspace, _private, _actor, _viewer = domain_api
    payload = {
        "investigation_id": workspace,
        "indicator_type": "domain",
        "value": "EXAMPLE.ORG.",
        "source": "explicit test fixture",
        "source_url": "https://example.org/feed",
        "confidence": 0.5,
    }
    first = client.post("/threat-indicators", json=payload)
    assert first.status_code == 201 and first.json()["value"] == "example.org"
    assert client.post("/threat-indicators", json=payload).json()["id"] == first.json()["id"]
    exported = client.get("/threat-indicators/export", params={"investigation_id": workspace}).json()
    assert len(exported) == 1 and exported[0]["source"] == "explicit test fixture"
    assert client.post("/threat-indicators", json={**payload, "value": "bad domain"}).status_code == 422


def test_indicator_validation_and_export_formula_neutralization():
    assert normalize_identifier("ip", "2001:0db8::1") == "2001:db8::1"
    assert normalize_identifier("domain", "EXAMPLE.ORG.") == "example.org"
    for kind, value in (
        ("sha256", "bad"),
        ("url", "file:///etc/passwd"),
        ("url", "https://user:secret@example.org"),
    ):
        with pytest.raises(ValueError):
            validate_indicator(kind, value)
    output = csv_export([{"value": '=HYPERLINK("bad")', "source": "\t=bad", "plain": "safe"}])
    assert "'=HYPERLINK" in output and "'\t=bad" in output
    assert json.loads(json.dumps({"data": "safe"})) == {"data": "safe"}
