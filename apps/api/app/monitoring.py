"""Database-backed recurring schedules, recovery and bounded outbox dispatch."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from croniter import CroniterBadCronError, CroniterBadDateError, croniter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.collection import (
    ACTIVE_STATUSES,
    add_alert,
    as_utc,
    create_job,
    dispatch_pending,
    validate_collection,
)
from app.config import settings
from app.db import SessionLocal
from app.models import CollectionJob, CollectionRun, Connector, Monitor, Timeline, utcnow


def validate_schedule(interval_seconds: int | None, cron: str | None) -> None:
    if (interval_seconds is None) == (cron is None):
        raise ValueError("Configure exatamente um intervalo ou uma expressão cron")
    if interval_seconds is not None and not 60 <= interval_seconds <= 31536000:
        raise ValueError("Intervalo deve estar entre 60 segundos e um ano")
    if cron is not None:
        if len(cron) > 120 or len(cron.split()) != 5:
            raise ValueError("Cron deve conter cinco campos e utiliza UTC")
        try:
            croniter(cron, utcnow(), max_years_between_matches=5).get_next(datetime)
        except (CroniterBadCronError, CroniterBadDateError, ValueError):
            raise ValueError("Expressão cron inválida ou sem execução nos próximos cinco anos") from None


def next_occurrence(monitor: Monitor, after: datetime) -> datetime:
    if monitor.interval_seconds is not None:
        return as_utc(after) + timedelta(seconds=monitor.interval_seconds)
    assert monitor.cron is not None
    return as_utc(croniter(monitor.cron, as_utc(after), max_years_between_matches=5).get_next(datetime))


def create_monitor(
    db: Session,
    *,
    investigation_id: str,
    connector_id: str,
    query: str,
    config: dict[str, Any] | None = None,
    interval_seconds: int | None = None,
    cron: str | None = None,
    alert_on_change: bool = True,
) -> Monitor:
    validate_schedule(interval_seconds, cron)
    validate_collection(db, connector_id, query, config or {})
    monitor = Monitor(
        investigation_id=investigation_id,
        connector_id=connector_id,
        query=query.strip(),
        config=config or {},
        interval_seconds=interval_seconds,
        cron=cron,
        alert_on_change=alert_on_change,
        enabled=True,
        next_run_at=utcnow(),
    )
    db.add(monitor)
    db.flush()
    return monitor


def pause_monitor(db: Session, monitor: Monitor) -> None:
    """Cancellation is durable; in-flight HTTP requests cannot commit effects."""
    monitor.enabled = False
    monitor.next_run_at = None
    jobs = db.scalars(
        select(CollectionJob)
        .where(CollectionJob.monitor_id == monitor.id, CollectionJob.status.in_(ACTIVE_STATUSES))
        .with_for_update()
    ).all()
    for job in jobs:
        job.status, job.finished_at = "cancelled", utcnow()
        for run in db.scalars(
            select(CollectionRun).where(CollectionRun.job_id == job.id, CollectionRun.status == "running")
        ):
            run.status, run.finished_at = "cancelled", utcnow()


def recover_stale_jobs(db: Session, now: datetime | None = None) -> int:
    instant = now or utcnow()
    jobs = db.scalars(
        select(CollectionJob)
        .where(
            (CollectionJob.status == "queued")
            & (CollectionJob.scheduled_at < instant - timedelta(seconds=600))
            | (CollectionJob.status == "running")
            & (CollectionJob.started_at < instant - timedelta(seconds=300))
        )
        .limit(100)
        .with_for_update(skip_locked=True)
    ).all()
    for job in jobs:
        monitor = db.get(Monitor, job.monitor_id) if job.monitor_id else None
        if monitor and not monitor.enabled:
            job.status, job.finished_at = "cancelled", instant
            continue
        for run in db.scalars(
            select(CollectionRun).where(CollectionRun.job_id == job.id, CollectionRun.status == "running")
        ):
            run.status, run.finished_at = "worker_lost", instant
            run.error = "Worker interrompido; execução recuperada pelo scheduler"
        if job.attempts >= settings.collection_max_attempts:
            job.status, job.finished_at = "dead_letter", instant
            job.last_error = "Máximo de tentativas atingido após perda do worker"
            add_alert(
                db,
                dedupe_key=f"job:worker_lost:{job.id}",
                investigation_id=job.investigation_id,
                monitor_id=job.monitor_id,
                event_type="collection_failed",
                title="Coleta encaminhada para dead-letter",
                details={"job_id": job.id, "error": job.last_error},
            )
        else:
            job.status, job.scheduled_at, job.task_id = "pending", instant, None
            job.last_error = "Execução recuperada após interrupção ou perda da mensagem"
    db.flush()
    return len(jobs)


def schedule_due_monitors(db: Session, now: datetime | None = None, limit: int = 100) -> int:
    """Allocate one unique job per due window under a monitor row lock.

    A delayed or restarted scheduler coalesces missed intervals into one fresh
    execution. Active jobs prevent overlap and unbounded queue growth.
    """
    instant = now or utcnow()
    due = db.scalars(
        select(Monitor)
        .join(Connector, Connector.id == Monitor.connector_id)
        .where(Monitor.enabled.is_(True), Monitor.next_run_at <= instant, Connector.enabled.is_(True))
        .order_by(Monitor.next_run_at)
        .limit(limit)
        .with_for_update(of=Monitor, skip_locked=True)
    ).all()
    created = 0
    for monitor in due:
        scheduled = as_utc(monitor.next_run_at or instant)
        monitor.next_run_at = next_occurrence(monitor, instant)
        if db.scalar(
            select(CollectionJob.id)
            .where(CollectionJob.monitor_id == monitor.id, CollectionJob.status.in_(ACTIVE_STATUSES))
            .limit(1)
        ):
            continue
        try:
            with db.begin_nested():
                job = create_job(
                    db,
                    investigation_id=monitor.investigation_id,
                    connector_id=monitor.connector_id,
                    query=monitor.query,
                    config=monitor.config,
                    monitor_id=monitor.id,
                    idempotency_key=f"monitor:{monitor.id}:{scheduled.isoformat()}",
                    scheduled_at=instant,
                )
                monitor.last_run_at = instant
                db.add(
                    Timeline(
                        investigation_id=monitor.investigation_id,
                        event_type="monitor_scheduled",
                        title="Monitor agendou uma coleta",
                        details={"monitor_id": monitor.id, "job_id": job.id},
                    )
                )
            created += 1
        except Exception as error:
            # Validation is retried after administrators fix configuration. Alerts
            # are suppressed for repeated failures of the same monitor.
            safe = (
                str(error)[:500]
                if isinstance(error, ValueError) or hasattr(error, "category")
                else "Configuração do monitor indisponível"
            )
            add_alert(
                db,
                dedupe_key=f"monitor:configuration:{monitor.id}",
                investigation_id=monitor.investigation_id,
                monitor_id=monitor.id,
                event_type="connector_failed",
                title="Monitor requer configuração do conector",
                details={"connector_id": monitor.connector_id, "error": safe},
            )
    db.flush()
    return created


@celery_app.task(name="app.monitoring.sweep", acks_late=True)
def sweep() -> dict[str, int]:
    with SessionLocal() as db:
        recovered = recover_stale_jobs(db)
        scheduled = schedule_due_monitors(db)
        db.commit()
        dispatched = dispatch_pending(db)
    return {"recovered": recovered, "scheduled": scheduled, "dispatched": dispatched}
