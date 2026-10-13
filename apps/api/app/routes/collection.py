"""Authorized REST controls for collection, schedules and public social profiles."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import (
    audit,
    current_user,
    encrypt_connector_settings,
    investigation_access,
    redact_connector_settings,
    require_admin,
)
from app.collection import (
    ACTIVE_STATUSES,
    create_job,
    dispatch_pending,
    effective_config,
    ensure_connector_rows,
    validate_collection,
)
from app.connectors.registry import registry
from app.connectors.security import ConnectorError
from app.db import get_db
from app.models import (
    CollectionJob,
    CollectionRun,
    Connector,
    ConnectorConfiguration,
    Investigation,
    InvestigationMember,
    Monitor,
    SocialProfile,
    Timeline,
    User,
    utcnow,
)
from app.monitoring import create_monitor, pause_monitor, validate_schedule

router = APIRouter(tags=["Coleta e monitoramento"])


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JobInput(Input):
    investigation_id: str = Field(min_length=1, max_length=36)
    connector_id: str = Field(min_length=1, max_length=80)
    query: str = Field(min_length=1, max_length=2048)
    config: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=5, ge=0, le=9)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


class MonitorInput(Input):
    investigation_id: str = Field(min_length=1, max_length=36)
    connector_id: str = Field(min_length=1, max_length=80)
    query: str = Field(min_length=1, max_length=2048)
    config: dict[str, Any] = Field(default_factory=dict)
    interval_seconds: int | None = Field(default=None, ge=60, le=31536000)
    cron: str | None = Field(default=None, max_length=120)
    alert_on_change: bool = True


class MonitorPatch(Input):
    enabled: bool | None = None
    query: str | None = Field(default=None, min_length=1, max_length=2048)
    config: dict[str, Any] | None = None
    interval_seconds: int | None = Field(default=None, ge=60, le=31536000)
    cron: str | None = Field(default=None, max_length=120)
    alert_on_change: bool | None = None


class ConnectorPatch(Input):
    enabled: bool


class ConnectorConfigurationInput(Input):
    settings: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class SocialInput(Input):
    investigation_id: str = Field(min_length=1, max_length=36)
    platform: str = Field(min_length=1, max_length=60)
    identifier: str = Field(min_length=1, max_length=1024)
    label: str = Field(default="", max_length=250)
    config: dict[str, Any] = Field(default_factory=dict)
    interval_seconds: int | None = Field(default=300, ge=60, le=31536000)


def serialize(record: Any) -> dict[str, Any]:
    return {column.name: getattr(record, column.name) for column in record.__table__.columns}


def scoped_statement(model: Any, db: Session, user: User, investigation_id: str | None) -> Any:
    statement = select(model)
    if investigation_id:
        investigation_access(db, user, investigation_id)
        return statement.where(model.investigation_id == investigation_id)
    if user.role == "admin":
        return statement
    membership = select(InvestigationMember.investigation_id).where(InvestigationMember.user_id == user.id)
    allowed = select(Investigation.id).where(
        or_(Investigation.owner_id == user.id, Investigation.id.in_(membership))
    )
    return statement.where(model.investigation_id.in_(allowed))


def page(db: Session, statement: Any, model: Any, limit: int, offset: int) -> dict[str, Any]:
    total = db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0
    records = db.scalars(statement.order_by(model.created_at.desc()).limit(limit).offset(offset)).all()
    return {"items": [serialize(item) for item in records], "total": total}


def find_authorized(db: Session, user: User, model: Any, record_id: str, write: bool = False) -> Any:
    record = db.get(model, record_id)
    if record is None:
        raise HTTPException(404, "Registro não encontrado")
    investigation_access(db, user, record.investigation_id, write=write)
    return record


def bad_request(error: Exception) -> HTTPException:
    return HTTPException(400, str(error))


@router.get("/connectors")
def list_connectors(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    ensure_connector_rows(db)
    db.commit()
    items = []
    for connector_id, connector in registry.items():
        row = db.get(Connector, connector_id)
        assert row is not None
        try:
            health = connector.health(effective_config(db, connector_id, {}))
        except (ValueError, HTTPException):
            health = {"status": "needs_configuration", "message": "Configuração protegida indisponível"}
        item = {
            **connector.descriptor(),
            "enabled": row.enabled,
            "configured": health.get("status") == "configured",
            "configuration_health": health,
            "health": row.health if row.enabled else "disabled",
            "last_success_at": row.last_success_at,
            "last_error_at": row.last_error_at,
            "last_error": row.last_error,
        }
        items.append(item)
    return {"items": items, "total": len(items)}


@router.patch("/connectors/{connector_id}")
def toggle_connector(
    connector_id: str,
    body: ConnectorPatch,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if connector_id not in registry:
        raise HTTPException(404, "Conector não encontrado")
    ensure_connector_rows(db)
    row = db.get(Connector, connector_id)
    assert row is not None
    row.enabled = body.enabled
    if not body.enabled:
        for job in db.scalars(
            select(CollectionJob)
            .where(CollectionJob.connector_id == connector_id, CollectionJob.status.in_(ACTIVE_STATUSES))
            .with_for_update()
        ):
            job.status, job.finished_at = "cancelled", utcnow()
            for run in db.scalars(
                select(CollectionRun).where(CollectionRun.job_id == job.id, CollectionRun.status == "running")
            ):
                run.status, run.finished_at = "cancelled", utcnow()
    audit(db, user, "connector.toggle", "connector", connector_id, details={"enabled": body.enabled})
    db.commit()
    return serialize(row)


@router.put("/connectors/{connector_id}/configuration")
def configure_connector(
    connector_id: str,
    body: ConnectorConfigurationInput,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if connector_id not in registry:
        raise HTTPException(404, "Conector não encontrado")
    registry[connector_id].validate_config(body.settings)
    ensure_connector_rows(db)
    row = db.scalar(select(ConnectorConfiguration).where(ConnectorConfiguration.connector_id == connector_id))
    encrypted = encrypt_connector_settings(body.settings)
    if row is None:
        row = ConnectorConfiguration(connector_id=connector_id, settings=encrypted, enabled=body.enabled)
        db.add(row)
    else:
        row.settings, row.enabled = encrypted, body.enabled
    audit(db, user, "connector.configure", "connector", connector_id)
    db.commit()
    return {
        "connector_id": connector_id,
        "enabled": row.enabled,
        "settings": redact_connector_settings(body.settings),
    }


@router.post("/jobs", status_code=201)
def add_job(
    body: JobInput, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict[str, Any]:
    investigation_access(db, user, body.investigation_id, write=True)
    try:
        job = create_job(db, **body.model_dump())
        audit(
            db,
            user,
            "job.create",
            "collection_job",
            job.id,
            body.investigation_id,
            details={"connector_id": job.connector_id},
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        # Handle simultaneous duplicate submissions without returning another
        # investigation's record or accepting a key for different parameters.
        try:
            job = create_job(db, **body.model_dump())
            db.commit()
        except (ValueError, ConnectorError) as error:
            raise HTTPException(409, str(error)) from None
    except (ValueError, ConnectorError) as error:
        raise bad_request(error) from None
    dispatch_pending(db)
    db.refresh(job)
    return serialize(job)


@router.get("/jobs")
def list_jobs(
    investigation_id: str | None = None,
    status: str | None = None,
    connector_id: str | None = None,
    monitor_id: str | None = None,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    statement = scoped_statement(CollectionJob, db, user, investigation_id)
    if status:
        statement = statement.where(CollectionJob.status == status)
    if connector_id:
        statement = statement.where(CollectionJob.connector_id == connector_id)
    if monitor_id:
        statement = statement.where(CollectionJob.monitor_id == monitor_id)
    return page(db, statement, CollectionJob, limit, offset)


@router.get("/jobs/{job_id}")
def get_job(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    job = find_authorized(db, user, CollectionJob, job_id)
    runs = db.scalars(
        select(CollectionRun)
        .where(CollectionRun.job_id == job.id)
        .order_by(CollectionRun.started_at.desc())
        .limit(50)
    ).all()
    return {**serialize(job), "runs": [serialize(run) for run in runs]}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(
    job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict[str, Any]:
    job = find_authorized(db, user, CollectionJob, job_id, write=True)
    job = db.scalar(
        select(CollectionJob)
        .where(CollectionJob.id == job.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert job is not None
    if job.status == "cancelled":
        return serialize(job)
    if job.status not in ACTIVE_STATUSES:
        raise HTTPException(409, "A tarefa já terminou")
    job.status, job.finished_at = "cancelled", utcnow()
    for run in db.scalars(
        select(CollectionRun).where(CollectionRun.job_id == job.id, CollectionRun.status == "running")
    ):
        run.status, run.finished_at = "cancelled", utcnow()
    audit(db, user, "job.cancel", "collection_job", job.id, job.investigation_id)
    db.commit()
    # Durable status controls cancellation; worker checks again before ingestion.
    return serialize(job)


@router.post("/jobs/{job_id}/retry")
def retry_job(
    job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict[str, Any]:
    job = find_authorized(db, user, CollectionJob, job_id, write=True)
    job = db.scalar(
        select(CollectionJob)
        .where(CollectionJob.id == job.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert job is not None
    if job.status not in {"failed", "dead_letter", "cancelled"}:
        raise HTTPException(409, "Somente tarefas canceladas ou com falha podem ser reenviadas")
    monitor = db.get(Monitor, job.monitor_id) if job.monitor_id else None
    if monitor and not monitor.enabled:
        raise HTTPException(409, "Retome o monitor antes de reenviar a tarefa")
    try:
        validate_collection(db, job.connector_id, job.query, job.config)
    except (ValueError, ConnectorError) as error:
        raise bad_request(error) from None
    job.status, job.attempts, job.task_id = "pending", 0, None
    job.scheduled_at, job.started_at, job.finished_at, job.last_error = utcnow(), None, None, None
    audit(db, user, "job.retry", "collection_job", job.id, job.investigation_id)
    db.commit()
    dispatch_pending(db)
    db.refresh(job)
    return serialize(job)


@router.post("/monitors", status_code=201)
def add_monitor(
    body: MonitorInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    investigation_access(db, user, body.investigation_id, write=True)
    try:
        monitor = create_monitor(db, **body.model_dump())
    except (ValueError, ConnectorError) as error:
        raise bad_request(error) from None
    audit(db, user, "monitor.create", "monitor", monitor.id, monitor.investigation_id)
    db.add(
        Timeline(
            investigation_id=monitor.investigation_id,
            event_type="monitor_created",
            title="Monitor recorrente criado",
            details={"monitor_id": monitor.id},
        )
    )
    db.commit()
    return serialize(monitor)


@router.get("/monitors")
def list_monitors(
    investigation_id: str | None = None,
    enabled: bool | None = None,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    statement = scoped_statement(Monitor, db, user, investigation_id)
    if enabled is not None:
        statement = statement.where(Monitor.enabled == enabled)
    return page(db, statement, Monitor, limit, offset)


@router.patch("/monitors/{monitor_id}")
def edit_monitor(
    monitor_id: str,
    body: MonitorPatch,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    monitor = find_authorized(db, user, Monitor, monitor_id, write=True)
    monitor = db.scalar(
        select(Monitor)
        .where(Monitor.id == monitor.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert monitor is not None
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(400, "Nenhuma alteração informada")
    interval, cron = monitor.interval_seconds, monitor.cron
    if "interval_seconds" in updates:
        interval = updates["interval_seconds"]
        if interval is not None and "cron" not in updates:
            cron = None
    if "cron" in updates:
        cron = updates["cron"]
        if cron is not None and "interval_seconds" not in updates:
            interval = None
    query = updates.get("query", monitor.query)
    config = updates.get("config", monitor.config)
    if (
        query is None
        or config is None
        or updates.get("enabled", True) is None
        or updates.get("alert_on_change", True) is None
    ):
        raise HTTPException(400, "Consulta, configuração e flags não podem ser nulas")
    try:
        validate_schedule(interval, cron)
        # A pause is always possible, even if the source is down or disabled.
        if updates != {"enabled": False}:
            validate_collection(db, monitor.connector_id, query, config)
    except (ValueError, ConnectorError) as error:
        raise bad_request(error) from None
    monitor.interval_seconds, monitor.cron = interval, cron
    monitor.query, monitor.config = query.strip(), config
    if "alert_on_change" in updates:
        monitor.alert_on_change = updates["alert_on_change"]
    if updates.get("enabled") is False:
        pause_monitor(db, monitor)
    elif updates.get("enabled") is True:
        monitor.enabled, monitor.next_run_at = True, utcnow()
    elif monitor.enabled and ("interval_seconds" in updates or "cron" in updates):
        monitor.next_run_at = utcnow()
    audit(
        db,
        user,
        "monitor.update",
        "monitor",
        monitor.id,
        monitor.investigation_id,
        details={"fields": sorted(updates)},
    )
    db.commit()
    return serialize(monitor)


@router.post("/monitors/{monitor_id}/run", status_code=201)
def run_monitor(
    monitor_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    monitor = find_authorized(db, user, Monitor, monitor_id, write=True)
    monitor = db.scalar(
        select(Monitor)
        .where(Monitor.id == monitor.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert monitor is not None
    if not monitor.enabled:
        raise HTTPException(409, "Monitor pausado")
    active = db.scalar(
        select(CollectionJob)
        .where(CollectionJob.monitor_id == monitor.id, CollectionJob.status.in_(ACTIVE_STATUSES))
        .limit(1)
    )
    if active:
        return serialize(active)
    try:
        job = create_job(
            db,
            investigation_id=monitor.investigation_id,
            connector_id=monitor.connector_id,
            query=monitor.query,
            config=monitor.config,
            monitor_id=monitor.id,
        )
    except (ValueError, ConnectorError) as error:
        raise bad_request(error) from None
    monitor.last_run_at = utcnow()
    audit(
        db, user, "monitor.run", "monitor", monitor.id, monitor.investigation_id, details={"job_id": job.id}
    )
    db.commit()
    dispatch_pending(db)
    db.refresh(job)
    return serialize(job)


@router.post("/social-profiles", status_code=201)
def add_social_profile(
    body: SocialInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    investigation_access(db, user, body.investigation_id, write=True)
    platform = body.platform.lower()
    if platform not in {"github", "gitlab", "bluesky", "mastodon", "instagram", "facebook"}:
        raise HTTPException(400, "Plataforma sem conector social oficial suportado")
    existing = db.scalar(
        select(SocialProfile).where(
            SocialProfile.investigation_id == body.investigation_id,
            SocialProfile.platform == platform,
            SocialProfile.identifier == body.identifier.strip(),
        )
    )
    if existing:
        return serialize(existing)
    try:
        registry[platform].validate_query(body.identifier.strip())
        monitor = (
            create_monitor(
                db,
                investigation_id=body.investigation_id,
                connector_id=platform,
                query=body.identifier,
                config=body.config,
                interval_seconds=body.interval_seconds,
            )
            if body.interval_seconds is not None
            else None
        )
    except (ValueError, ConnectorError) as error:
        raise bad_request(error) from None
    profile = SocialProfile(
        investigation_id=body.investigation_id,
        platform=platform,
        identifier=body.identifier.strip(),
        label=body.label,
        monitor_id=monitor.id if monitor else None,
    )
    db.add(profile)
    db.flush()
    audit(db, user, "social_profile.create", "social_profile", profile.id, profile.investigation_id)
    db.commit()
    return serialize(profile)


@router.get("/social-profiles")
def list_social_profiles(
    investigation_id: str | None = None,
    platform: str | None = None,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    statement = scoped_statement(SocialProfile, db, user, investigation_id)
    if platform:
        statement = statement.where(SocialProfile.platform == platform)
    return page(db, statement, SocialProfile, limit, offset)
