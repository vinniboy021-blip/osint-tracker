"""Durable collection jobs and immutable, attributable observation snapshots.

An acknowledged Celery message is never the durable job record. Every task claims
its PostgreSQL row first and commits all effects with a fencing check afterwards.
Duplicate deliveries, cancellations and stale workers consequently cannot ingest
the same job twice or overwrite the result of a newer execution.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import settings
from app.connectors.registry import registry
from app.db import SessionLocal
from app.models import (
    Alert,
    CollectionJob,
    CollectionRun,
    Connector,
    ConnectorConfiguration,
    Entity,
    Monitor,
    NotificationDelivery,
    Observation,
    Timeline,
    utcnow,
)

logger = logging.getLogger(__name__)
ACTIVE_STATUSES = ("pending", "queued", "running")


def as_utc(value: datetime) -> datetime:
    """SQLite fixtures return naive UTC; PostgreSQL uses timezone-aware dates."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def ensure_connector_rows(db: Session) -> None:
    for connector_id, connector in registry.items():
        if db.get(Connector, connector_id) is None:
            try:
                with db.begin_nested():
                    db.add(
                        Connector(
                            id=connector_id,
                            name=connector.descriptor().get("name", connector_id),
                            enabled=True,
                        )
                    )
                    db.flush()
            except IntegrityError:
                # Another API/worker seeded this registry row concurrently.
                pass


def effective_config(db: Session, connector_id: str, config: dict[str, Any]) -> dict[str, Any]:
    from app.auth import decrypt_connector_settings

    configured = db.scalar(
        select(ConnectorConfiguration).where(
            ConnectorConfiguration.connector_id == connector_id,
            ConnectorConfiguration.enabled.is_(True),
        )
    )
    # Admin connector secrets are encrypted at rest and never copied into jobs,
    # reports or observations. Environment credentials remain supported too.
    return {**(decrypt_connector_settings(configured.settings) if configured else {}), **config}


def validate_collection(db: Session, connector_id: str, query: str, config: dict[str, Any]) -> dict[str, Any]:
    if connector_id not in registry:
        raise ValueError("Conector desconhecido")
    if len(query) > 2048 or not query.strip():
        raise ValueError("Consulta vazia ou acima do limite de 2048 caracteres")
    if len(json.dumps(config, ensure_ascii=False, default=str)) > 32768:
        raise ValueError("Configuração acima do limite de 32 KiB")
    ensure_connector_rows(db)
    persisted = db.get(Connector, connector_id)
    if persisted is None or not persisted.enabled:
        raise ValueError("Conector desabilitado")
    connector = registry[connector_id]
    descriptor = connector.descriptor()
    schema = descriptor.get("config_schema", {})
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    from app.auth import is_secret_field

    secret_keys = {"token", "access_token", "authorization_token", "password", "api_key", "secret"}
    secret_keys.update(
        key for key, value in properties.items() if isinstance(value, dict) and value.get("writeOnly")
    )

    def contains_secret(value: Any) -> bool:
        if isinstance(value, dict):
            return any(
                is_secret_field(key) or key in secret_keys or contains_secret(item)
                for key, item in value.items()
            )
        return isinstance(value, list) and any(contains_secret(item) for item in value)

    if contains_secret(config):
        raise ValueError("Credenciais devem ser configuradas no ambiente, nunca em tarefas")
    merged = effective_config(db, connector_id, config)
    connector.validate_query(query.strip())
    connector.validate_config(merged)
    return config


def create_job(
    db: Session,
    *,
    investigation_id: str,
    connector_id: str,
    query: str,
    config: dict[str, Any] | None = None,
    priority: int = 5,
    idempotency_key: str | None = None,
    monitor_id: str | None = None,
    scheduled_at: datetime | None = None,
) -> CollectionJob:
    options = config or {}
    validate_collection(db, connector_id, query, options)
    if not 0 <= priority <= 9:
        raise ValueError("Prioridade deve estar entre 0 e 9")
    key = idempotency_key or str(uuid4())
    if len(key) > 200:
        raise ValueError("Chave de idempotência acima de 200 caracteres")
    existing = db.scalar(select(CollectionJob).where(CollectionJob.idempotency_key == key))
    if existing:
        if (
            existing.investigation_id != investigation_id
            or existing.connector_id != connector_id
            or existing.query != query.strip()
            or existing.config != options
            or existing.monitor_id != monitor_id
        ):
            raise ValueError("Chave de idempotência já usada para outra operação")
        return existing
    job = CollectionJob(
        investigation_id=investigation_id,
        connector_id=connector_id,
        query=query.strip(),
        config=options,
        priority=priority,
        idempotency_key=key,
        monitor_id=monitor_id,
        scheduled_at=scheduled_at or utcnow(),
        status="pending",
    )
    db.add(job)
    db.flush()
    return job


def dispatch_pending(db: Session, limit: int = 50, now: datetime | None = None) -> int:
    """Transactional outbox sweep; a broker outage leaves pending rows intact.

    A publish followed by a failed DB commit can deliver twice. run_collection's
    row lock makes this safe. Holding the lock through publish means a consumer
    cannot claim a job before its queued state is committed.
    """
    instant = now or utcnow()
    jobs = db.scalars(
        select(CollectionJob)
        .where(CollectionJob.status == "pending", CollectionJob.scheduled_at <= instant)
        .order_by(CollectionJob.priority.desc(), CollectionJob.scheduled_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()
    sent = 0
    for job in jobs:
        monitor = db.get(Monitor, job.monitor_id) if job.monitor_id else None
        if monitor and not monitor.enabled:
            job.status = "cancelled"
            job.finished_at = instant
            continue
        task_id = str(uuid4())
        try:
            run_collection.apply_async(
                args=[job.id],
                task_id=task_id,
                priority=9 - job.priority,
                retry=False,
            )
        except Exception:
            # Exception representations may contain URLs or credentials from the
            # transport. Neither logs nor the job exposes those representations.
            logger.warning(
                "collection_dispatch_deferred",
                extra={
                    "job_id": job.id,
                    "investigation_id": job.investigation_id,
                    "connector_id": job.connector_id,
                },
            )
            job.last_error = "Fila indisponível; a tarefa permanece no outbox para recuperação automática"
            break
        job.task_id = task_id
        job.status = "queued"
        job.scheduled_at = instant
        job.last_error = None
        sent += 1
    db.commit()
    return sent


def _canonical_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _canonical_data(item)
            for key, item in value.items()
            if key not in {"ingested_at", "retrieved_at", "fetched_at", "collected_at"}
        }
    if isinstance(value, list):
        return [_canonical_data(item) for item in value]
    return value


def observation_fingerprint(observation: Any) -> str:
    raw = {
        "identity": observation.external_id or observation.source_url,
        "source": observation.source_name,
        "data": _canonical_data(observation.data),
    }
    encoded = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _entity(db: Session, job: CollectionJob, item: Any) -> Entity | None:
    entity_type = getattr(item, "entity_type", None)
    value = getattr(item, "entity_value", None)
    if not entity_type or not value:
        return None
    # Exact identifier equality only. This routine never uses names or photos to
    # associate people. Hypotheses and reversible manual review live in correlation.
    from app.intelligence import normalize_identifier

    canonical = normalize_identifier(entity_type, str(value))
    entity = db.scalar(
        select(Entity).where(
            Entity.investigation_id == job.investigation_id,
            Entity.type == entity_type,
            Entity.canonical_value == canonical,
        )
    )
    if entity:
        return entity
    try:
        with db.begin_nested():
            entity = Entity(
                investigation_id=job.investigation_id,
                type=entity_type,
                canonical_value=canonical,
                label=(getattr(item, "entity_label", None) or str(value))[:250],
                attributes={"source": item.source_name},
            )
            db.add(entity)
            db.flush()
        return entity
    except IntegrityError:
        return db.scalar(
            select(Entity).where(
                Entity.investigation_id == job.investigation_id,
                Entity.type == entity_type,
                Entity.canonical_value == canonical,
            )
        )


def add_alert(db: Session, *, dedupe_key: str, **values: Any) -> Alert | None:
    if db.scalar(select(Alert.id).where(Alert.dedupe_key == dedupe_key)):
        return None
    try:
        with db.begin_nested():
            alert = Alert(dedupe_key=dedupe_key, **values)
            db.add(alert)
            db.flush()
            db.add(NotificationDelivery(alert_id=alert.id, channel="internal", status="delivered"))
        return alert
    except IntegrityError:
        return None


def ingest_observations(db: Session, job: CollectionJob, items: list[Any]) -> int:
    monitor = db.get(Monitor, job.monitor_id) if job.monitor_id else None
    count = 0
    if len(items) > settings.collection_max_records:
        raise ValueError("Conector excedeu o limite de resultados por coleta")
    for item in items:
        if len(json.dumps(item.data, default=str)) > 256 * 1024:
            raise ValueError("Observação excedeu o limite de 256 KiB")
        identity = item.external_id or item.source_url
        previous = db.scalar(
            select(Observation)
            .where(
                Observation.investigation_id == job.investigation_id,
                Observation.connector_id == job.connector_id,
                Observation.external_id == identity,
            )
            .order_by(Observation.collected_at.desc(), Observation.created_at.desc())
            .limit(1)
        )
        if previous and _canonical_data(previous.data) == _canonical_data(item.data):
            continue
        # The predecessor is part of the immutable snapshot identity so a real
        # A -> B -> A reversion remains visible. Repeated unchanged snapshots and
        # concurrent delivery of an identical transition still deduplicate.
        fingerprint = hashlib.sha256(
            (observation_fingerprint(item) + ":" + (previous.fingerprint if previous else "")).encode()
        ).hexdigest()
        entity = _entity(db, job, item)
        observation = Observation(
            investigation_id=job.investigation_id,
            job_id=job.id,
            monitor_id=job.monitor_id,
            connector_id=job.connector_id,
            entity_id=entity.id if entity else None,
            source_url=item.source_url,
            source_name=item.source_name,
            acquisition_method=item.acquisition_method,
            collected_at=as_utc(item.collected_at),
            external_id=identity,
            fingerprint=fingerprint,
            data=item.data,
        )
        try:
            with db.begin_nested():
                db.add(observation)
                db.flush()
        except IntegrityError:
            # Two different jobs can encounter the same immutable snapshot.
            continue
        count += 1
        if monitor and monitor.alert_on_change:
            changed_keys = sorted(
                key
                for key in set(previous.data if previous else {}) | set(item.data)
                if _canonical_data((previous.data if previous else {}).get(key))
                != _canonical_data(item.data.get(key))
                and key not in {"ingested_at", "retrieved_at", "fetched_at", "collected_at"}
            )
            add_alert(
                db,
                dedupe_key=f"observation:{observation.id}",
                investigation_id=job.investigation_id,
                monitor_id=monitor.id,
                observation_id=observation.id,
                event_type="data_changed" if previous else "new_observation",
                title="Alteração detectada" if previous else "Nova observação coletada",
                details={
                    "observation_id": observation.id,
                    "previous_observation_id": previous.id if previous else None,
                    "source_url": observation.source_url,
                    "connector_id": job.connector_id,
                    "changed_fields": changed_keys,
                },
            )
    return count


def _rate_limit(connector_id: str) -> float:
    """Coordinate starts across workers; connector HTTP clients also limit requests."""
    client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
    try:
        accepted = client.set(f"osint:collection:start:{connector_id}", "1", nx=True, px=1000)
        return 0 if accepted else 1.5
    finally:
        client.close()


def _owns_run(db: Session, job: CollectionJob, run_id: str) -> bool:
    latest = db.scalar(
        select(CollectionRun.id)
        .where(CollectionRun.job_id == job.id)
        .order_by(CollectionRun.started_at.desc(), CollectionRun.created_at.desc())
        .limit(1)
    )
    return job.status == "running" and latest == run_id


def _fail_run(job_id: str, run_id: str, *, retryable: bool, message: str) -> dict[str, Any]:
    with SessionLocal() as db:
        job = db.scalar(select(CollectionJob).where(CollectionJob.id == job_id).with_for_update())
        if job is None or not _owns_run(db, job, run_id):
            return {"status": "superseded"}
        run = db.get(CollectionRun, run_id)
        assert run is not None
        now = utcnow()
        run.status, run.error, run.finished_at = "failed", message, now
        job.last_error = message
        connector = db.get(Connector, job.connector_id)
        if connector:
            connector.health = "error"
            connector.last_error = message
            connector.last_error_at = connector.last_checked_at = now
        if retryable and job.attempts < settings.collection_max_attempts:
            job.status = "pending"
            job.scheduled_at = now + timedelta(seconds=min(900, 30 * 2 ** (job.attempts - 1)))
            job.task_id = None
        else:
            job.status = "dead_letter" if retryable else "failed"
            job.finished_at = now
            add_alert(
                db,
                dedupe_key=f"job:failed:{job.id}:{job.attempts}",
                investigation_id=job.investigation_id,
                monitor_id=job.monitor_id,
                event_type="collection_failed",
                title="Falha persistente de coleta" if retryable else "Coleta não pôde ser executada",
                details={"job_id": job.id, "connector_id": job.connector_id, "error": message},
            )
        db.commit()
        return {"status": job.status}


@celery_app.task(name="app.collection.run_collection", bind=True, acks_late=True)
def run_collection(self: Any, job_id: str) -> dict[str, Any]:
    with SessionLocal() as db:
        job = db.scalar(select(CollectionJob).where(CollectionJob.id == job_id).with_for_update())
        if job is None or job.status not in {"pending", "queued"}:
            return {"status": "skipped"}
        if as_utc(job.scheduled_at) > utcnow():
            return {"status": "deferred"}
        monitor = db.get(Monitor, job.monitor_id) if job.monitor_id else None
        connector_row = db.get(Connector, job.connector_id)
        if (monitor and not monitor.enabled) or not connector_row or not connector_row.enabled:
            job.status = "cancelled"
            job.finished_at = utcnow()
            db.commit()
            return {"status": "cancelled"}
        job.status = "running"
        job.attempts += 1
        job.started_at = utcnow()
        run = CollectionRun(job_id=job.id, status="running", started_at=job.started_at)
        db.add(run)
        db.flush()
        run_id = run.id
        connector_id, query = job.connector_id, job.query
        config = effective_config(db, connector_id, job.config)
        db.commit()

    try:
        delay = _rate_limit(connector_id)
        if delay:
            with SessionLocal() as db:
                job = db.scalar(select(CollectionJob).where(CollectionJob.id == job_id).with_for_update())
                if job and _owns_run(db, job, run_id):
                    job.status = "pending"
                    job.attempts -= 1
                    job.scheduled_at = utcnow() + timedelta(seconds=delay)
                    job.task_id = None
                    deferred_run = db.get(CollectionRun, run_id)
                    assert deferred_run is not None
                    deferred_run.status, deferred_run.finished_at = "deferred", utcnow()
                    db.commit()
            return {"status": "deferred"}
        connector = registry[connector_id]
        connector.validate_query(query)
        connector.validate_config(config)
        from app.connectors import configure_rate_limiter

        rate_client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
        configure_rate_limiter(rate_client)
        try:
            items = connector.collect(query, config)
        finally:
            rate_client.close()
        with SessionLocal() as db:
            job = db.scalar(select(CollectionJob).where(CollectionJob.id == job_id).with_for_update())
            if job is None or not _owns_run(db, job, run_id):
                return {"status": "superseded"}
            # Pausing a monitor while a request is in flight also suppresses effects.
            monitor = db.get(Monitor, job.monitor_id) if job.monitor_id else None
            source = db.get(Connector, connector_id)
            if (monitor and not monitor.enabled) or not source or not source.enabled:
                job.status, job.finished_at = "cancelled", utcnow()
                cancelled_run = db.get(CollectionRun, run_id)
                if cancelled_run:
                    cancelled_run.status, cancelled_run.finished_at = "cancelled", utcnow()
                db.commit()
                return {"status": "cancelled"}
            inserted = ingest_observations(db, job, items)
            now = utcnow()
            job.status, job.finished_at, job.last_error = "succeeded", now, None
            succeeded_run = db.get(CollectionRun, run_id)
            assert succeeded_run is not None
            succeeded_run.status, succeeded_run.result_count, succeeded_run.finished_at = (
                "succeeded",
                inserted,
                now,
            )
            row = db.get(Connector, connector_id)
            if row:
                row.health, row.last_error = "healthy", None
                row.last_success_at = row.last_checked_at = now
            db.add(
                Timeline(
                    investigation_id=job.investigation_id,
                    event_type="collection_completed",
                    title="Coleta concluída",
                    details={"job_id": job.id, "connector_id": connector_id, "new_observations": inserted},
                )
            )
            db.commit()
            return {"status": "succeeded", "new_observations": inserted}
    except Exception as error:
        # Connector errors explicitly expose safe messages; arbitrary error text is
        # never persisted because it may include bearer tokens or source payloads.
        retryable = bool(getattr(error, "retryable", True))
        category = getattr(error, "category", None)
        safe_message = (
            str(error)[:500] if category is not None else "Falha durante a coleta; consulte o ID da execução"
        )
        logger.warning("collection_failed", extra={"job_id": job_id, "run_id": run_id})
        return _fail_run(job_id, run_id, retryable=retryable, message=safe_message)
