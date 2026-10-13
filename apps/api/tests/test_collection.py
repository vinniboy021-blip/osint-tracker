"""Fixtures here are explicit tests, never application observations or demo data."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app import collection
from app.connectors.base import NormalizedObservation
from app.connectors.security import ConnectorError
from app.models import (
    Alert,
    CollectionJob,
    CollectionRun,
    Connector,
    Entity,
    Investigation,
    Observation,
    User,
)
from app.routes import collection as routes


class FixtureConnector:
    """An identified mock source used only by tests."""

    def __init__(self) -> None:
        self.calls = 0
        self.items = [observation({"title": "test fixture", "followers": 10})]
        self.error: Exception | None = None
        self.callback: Any = None

    def descriptor(self) -> dict[str, Any]:
        return {"id": "test", "name": "TEST FIXTURE", "config_schema": {"properties": {}}}

    def validate_query(self, query: str) -> str:
        if not query:
            raise ConnectorError("Empty test query")
        return query

    def validate_config(self, config: dict[str, Any]) -> None:
        if config.get("invalid"):
            raise ConnectorError("Invalid test configuration")

    def health(self, config: dict[str, Any]) -> dict[str, str]:
        return {"status": "configured"}

    def collect(self, query: str, config: dict[str, Any]) -> list[NormalizedObservation]:
        self.calls += 1
        if self.callback:
            self.callback()
        if self.error:
            raise self.error
        return self.items


def observation(data: dict[str, Any], external_id: str = "fixture:1") -> NormalizedObservation:
    return NormalizedObservation(
        source_name="TEST FIXTURE",
        source_url="https://example.com/explicit-test-fixture",
        external_id=external_id,
        data=data,
        collected_at=datetime.now(UTC),
        entity_type="domain",
        entity_value="EXAMPLE.com",
        entity_label="Explicit test domain",
    )


@pytest.fixture
def source(db: Any, monkeypatch: Any) -> FixtureConnector:
    connector = FixtureConnector()
    monkeypatch.setattr(collection, "registry", {"test": connector})
    monkeypatch.setattr(routes, "registry", {"test": connector})
    monkeypatch.setattr(collection, "SessionLocal", sessionmaker(bind=db.get_bind(), expire_on_commit=False))
    monkeypatch.setattr(collection, "_rate_limit", lambda connector_id: 0)
    monkeypatch.setattr("app.connectors.configure_rate_limiter", lambda client: None)
    monkeypatch.setattr(routes, "dispatch_pending", lambda session: 0)
    return connector


def job(db: Any, investigation: Any, **kwargs: Any) -> CollectionJob:
    record = collection.create_job(
        db, investigation_id=investigation.id, connector_id="test", query="explicit fixture", **kwargs
    )
    db.commit()
    return record


def count(db: Any, model: Any) -> int:
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


def test_worker_persists_provenance_entities_and_deduplicates(
    db: Any, investigation: Any, source: Any
) -> None:
    record = job(db, investigation)
    assert collection.run_collection.run(record.id) == {"status": "succeeded", "new_observations": 1}
    db.expire_all()
    assert count(db, Observation) == 1
    item = db.scalar(select(Observation))
    assert item.source_name == "TEST FIXTURE"
    assert item.source_url == "https://example.com/explicit-test-fixture"
    assert item.job_id == record.id
    assert db.scalar(select(Entity)).canonical_value == "example.com"
    assert db.scalar(select(CollectionRun)).status == "succeeded"
    assert collection.run_collection.run(record.id) == {"status": "skipped"}
    second = job(db, investigation)
    assert collection.run_collection.run(second.id)["new_observations"] == 0
    assert source.calls == 2
    assert count(db, Observation) == 1


def test_idempotency_key_reuses_only_matching_operation(db: Any, investigation: Any, source: Any) -> None:
    first = job(db, investigation, idempotency_key="explicit-fixture-key")
    second = job(db, investigation, idempotency_key="explicit-fixture-key")
    assert first.id == second.id
    with pytest.raises(ValueError, match="outra operação"):
        collection.create_job(
            db,
            investigation_id=investigation.id,
            connector_id="test",
            query="different",
            idempotency_key="explicit-fixture-key",
        )
    assert count(db, CollectionJob) == 1


def test_transport_outage_retains_durable_pending_job(
    db: Any, investigation: Any, source: Any, monkeypatch: Any
) -> None:
    record = job(db, investigation)

    def unavailable(*args: Any, **kwargs: Any) -> None:
        raise ConnectionError("Test transport outage: not a source result")

    monkeypatch.setattr(collection.run_collection, "apply_async", unavailable)
    assert collection.dispatch_pending(db) == 0
    db.refresh(record)
    assert record.status == "pending"
    assert record.task_id is None
    assert source.calls == 0


def test_priority_dispatch_uses_inverted_redis_priority(
    db: Any, investigation: Any, source: Any, monkeypatch: Any
) -> None:
    low = job(db, investigation, priority=1)
    high = job(db, investigation, priority=9)
    messages = []
    monkeypatch.setattr(collection.run_collection, "apply_async", lambda **kwargs: messages.append(kwargs))
    assert collection.dispatch_pending(db) == 2
    assert [item["args"][0] for item in messages] == [high.id, low.id]
    assert [item["priority"] for item in messages] == [0, 8]
    db.refresh(high)
    assert high.status == "queued"


def test_retry_backoff_and_dead_letter_are_durable(
    db: Any, investigation: Any, source: Any, monkeypatch: Any
) -> None:
    monkeypatch.setattr(collection.settings, "collection_max_attempts", 2)
    source.error = ConnectorError("Explicit test outage", category="upstream", retryable=True)
    record = job(db, investigation)
    before = datetime.now(UTC)
    assert collection.run_collection.run(record.id)["status"] == "pending"
    db.expire_all()
    db.refresh(record)
    assert record.attempts == 1
    assert collection.as_utc(record.scheduled_at) >= before + timedelta(seconds=29)
    record.scheduled_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert collection.run_collection.run(record.id)["status"] == "dead_letter"
    db.expire_all()
    assert count(db, Observation) == 0
    assert count(db, CollectionRun) == 2
    assert count(db, Alert) == 1


def test_permanent_failure_does_not_retry_or_expose_arbitrary_error_text(
    db: Any, investigation: Any, source: Any
) -> None:
    source.error = ConnectorError("Missing official permission", category="authorization")
    record = job(db, investigation)
    assert collection.run_collection.run(record.id)["status"] == "failed"
    source.error = RuntimeError("Do not expose TEST_SECRET=123456")
    second = job(db, investigation)
    assert collection.run_collection.run(second.id)["status"] == "pending"
    db.refresh(second)
    assert "TEST_SECRET" not in second.last_error


def test_cancel_before_execution_and_during_collection_prevents_effects(
    db: Any, investigation: Any, source: Any
) -> None:
    record = job(db, investigation)
    record.status = "cancelled"
    db.commit()
    assert collection.run_collection.run(record.id)["status"] == "skipped"
    assert source.calls == 0
    in_flight = job(db, investigation)

    def cancel_in_flight() -> None:
        with collection.SessionLocal() as cancel_db:
            target = cancel_db.get(CollectionJob, in_flight.id)
            target.status = "cancelled"
            cancel_db.commit()

    source.callback = cancel_in_flight
    assert collection.run_collection.run(in_flight.id)["status"] == "superseded"
    assert count(db, Observation) == 0


def test_rate_backpressure_does_not_consume_collection_attempt(
    db: Any, investigation: Any, source: Any, monkeypatch: Any
) -> None:
    monkeypatch.setattr(collection, "_rate_limit", lambda connector_id: 1.5)
    record = job(db, investigation)
    assert collection.run_collection.run(record.id)["status"] == "deferred"
    db.refresh(record)
    assert record.attempts == 0
    assert record.status == "pending"
    assert source.calls == 0


def test_job_configs_reject_nested_credentials(db: Any, investigation: Any, source: Any) -> None:
    with pytest.raises(ValueError, match="Credenciais"):
        job(db, investigation, config={"nested": {"token": "explicit test secret"}})


def test_disabled_connector_cannot_execute(db: Any, investigation: Any, source: Any) -> None:
    record = job(db, investigation)
    db.get(Connector, "test").enabled = False
    db.commit()
    assert collection.run_collection.run(record.id)["status"] == "cancelled"
    assert source.calls == 0


def test_job_api_and_cross_investigation_authorization(
    client: Any, db: Any, user: Any, investigation: Any, source: Any
) -> None:
    user.role = "analyst"
    other = User(email="other-fixture@example.com", password_hash="test fixture hash", role="analyst")
    db.add(other)
    db.flush()
    hidden = Investigation(title="Private test investigation", owner_id=other.id)
    db.add(hidden)
    db.flush()
    hidden_job = collection.create_job(db, investigation_id=hidden.id, connector_id="test", query="test")
    db.commit()
    body = {"investigation_id": investigation.id, "connector_id": "test", "query": "test"}
    response = client.post("/api/v1/jobs", json=body)
    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert client.get(f"/api/v1/jobs/{hidden_job.id}").status_code == 404
    assert client.post(f"/api/v1/jobs/{hidden_job.id}/cancel").status_code == 404
    assert client.post("/api/v1/jobs", json={**body, "investigation_id": hidden.id}).status_code == 404
    visible = client.get("/api/v1/jobs").json()
    assert visible["total"] == 1
    user.role = "viewer"
    db.commit()
    assert client.post("/api/v1/jobs", json=body).status_code == 403
