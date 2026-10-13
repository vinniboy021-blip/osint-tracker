"""Relational contracts shared by HTTP handlers and asynchronous workers."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


JSONType = JSON().with_variant(JSONB(), "postgresql")


class Record:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class User(Record, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('admin','analyst','viewer')", name="valid_role"),)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default="analyst")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Role(Record, Base):
    __tablename__ = "roles"
    name: Mapped[str] = mapped_column(String(50), unique=True)


class Permission(Record, Base):
    __tablename__ = "permissions"
    name: Mapped[str] = mapped_column(String(100), unique=True)


role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", String(36), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", String(36), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


class AuthSession(Record, Base):
    __tablename__ = "sessions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Investigation(Record, Base):
    __tablename__ = "investigations"
    title: Mapped[str] = mapped_column(String(250))
    objective: Mapped[str] = mapped_column(Text, default="")
    scope: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class InvestigationMember(Record, Base):
    __tablename__ = "investigation_members"
    __table_args__ = (
        UniqueConstraint("investigation_id", "user_id"),
        CheckConstraint("role IN ('owner','editor','viewer')", name="valid_role"),
    )
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="viewer")


class Connector(Base):
    __tablename__ = "connectors"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    health: Mapped[str] = mapped_column(String(30), default="unknown")
    last_error: Mapped[str | None] = mapped_column(Text)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConnectorConfiguration(Record, Base):
    __tablename__ = "connector_configurations"
    connector_id: Mapped[str] = mapped_column(
        ForeignKey("connectors.id", ondelete="CASCADE"), index=True, unique=True
    )
    settings: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Monitor(Record, Base):
    __tablename__ = "monitors"
    __table_args__ = (
        CheckConstraint("interval_seconds IS NULL OR interval_seconds >= 60", name="minimum_interval"),
        CheckConstraint("(interval_seconds IS NULL) <> (cron IS NULL)", name="one_schedule"),
        Index("ix_monitors_due", "enabled", "next_run_at"),
    )
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    connector_id: Mapped[str] = mapped_column(ForeignKey("connectors.id", ondelete="RESTRICT"), index=True)
    query: Mapped[str] = mapped_column(String(2048))
    config: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    interval_seconds: Mapped[int | None] = mapped_column(Integer)
    cron: Mapped[str | None] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    alert_on_change: Mapped[bool] = mapped_column(Boolean, default=True)


class CollectionJob(Record, Base):
    __tablename__ = "collection_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','queued','running','succeeded','failed','cancelled','dead_letter')",
            name="valid_status",
        ),
        CheckConstraint("priority BETWEEN 0 AND 9", name="valid_priority"),
        Index("ix_collection_jobs_recovery", "status", "scheduled_at"),
    )
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    connector_id: Mapped[str] = mapped_column(ForeignKey("connectors.id", ondelete="RESTRICT"), index=True)
    query: Mapped[str] = mapped_column(String(2048))
    config: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=5)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    task_id: Mapped[str | None] = mapped_column(String(100), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True, default=new_id)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    monitor_id: Mapped[str | None] = mapped_column(ForeignKey("monitors.id", ondelete="SET NULL"), index=True)


class CollectionRun(Record, Base):
    __tablename__ = "collection_runs"
    job_id: Mapped[str] = mapped_column(ForeignKey("collection_jobs.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(30))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class Entity(Record, Base):
    __tablename__ = "entities"
    __table_args__ = (UniqueConstraint("investigation_id", "type", "canonical_value"),)
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(60), index=True)
    canonical_value: Mapped[str] = mapped_column(String(1024))
    label: Mapped[str] = mapped_column(String(250))
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class EntityAlias(Record, Base):
    __tablename__ = "entity_aliases"
    __table_args__ = (UniqueConstraint("entity_id", "value"),)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), index=True)
    value: Mapped[str] = mapped_column(String(1024))
    source: Mapped[str] = mapped_column(String(200), default="manual")


class Observation(Record, Base):
    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint("investigation_id", "connector_id", "fingerprint"),
        Index("ix_observations_investigation_time", "investigation_id", "collected_at"),
    )
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[str | None] = mapped_column(
        ForeignKey("collection_jobs.id", ondelete="SET NULL"), index=True
    )
    monitor_id: Mapped[str | None] = mapped_column(ForeignKey("monitors.id", ondelete="SET NULL"), index=True)
    connector_id: Mapped[str] = mapped_column(ForeignKey("connectors.id", ondelete="RESTRICT"), index=True)
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("entities.id", ondelete="SET NULL"), index=True)
    source_url: Mapped[str] = mapped_column(Text)
    source_name: Mapped[str] = mapped_column(String(150))
    acquisition_method: Mapped[str] = mapped_column(String(100))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    external_id: Mapped[str] = mapped_column(String(1024))
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class EntityRelationship(Record, Base):
    __tablename__ = "entity_relationships"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="valid_confidence"),
        CheckConstraint("status IN ('confirmed','probable','unverified','rejected')", name="valid_status"),
        CheckConstraint("source_entity_id <> target_entity_id", name="distinct_entities"),
    )
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    source_entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), index=True)
    target_entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), index=True)
    relationship_type: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="unverified")
    confidence: Mapped[float] = mapped_column(Float, default=0)
    explanation: Mapped[str] = mapped_column(Text, default="")
    evidence_ids: Mapped[list[str]] = mapped_column(JSONType, default=list)


class CorrelationCandidate(Record, Base):
    __tablename__ = "correlation_candidates"
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 1", name="valid_score"),
        UniqueConstraint("investigation_id", "source_entity_id", "target_entity_id", "rule"),
    )
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    source_entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), index=True)
    target_entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), index=True)
    score: Mapped[float] = mapped_column(Float)
    rule: Mapped[str] = mapped_column(String(100))
    explanation: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class CorrelationReview(Record, Base):
    __tablename__ = "correlation_reviews"
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("correlation_candidates.id", ondelete="CASCADE"), index=True
    )
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    decision: Mapped[str] = mapped_column(String(30))
    notes: Mapped[str] = mapped_column(Text, default="")


class Evidence(Record, Base):
    __tablename__ = "evidence"
    __table_args__ = (CheckConstraint("size_bytes >= 0", name="valid_size"),)
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("entities.id", ondelete="SET NULL"), index=True)
    filename: Mapped[str] = mapped_column(String(250))
    content_type: Mapped[str] = mapped_column(String(150))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    source_url: Mapped[str] = mapped_column(Text, default="")
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    notes: Mapped[str] = mapped_column(Text, default="")
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class EvidenceVersion(Record, Base):
    __tablename__ = "evidence_versions"
    __table_args__ = (UniqueConstraint("evidence_id", "version"),)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(500))
    size_bytes: Mapped[int] = mapped_column(Integer)


class Timeline(Record, Base):
    __tablename__ = "timelines"
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(250))
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class Alert(Record, Base):
    __tablename__ = "alerts"
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    monitor_id: Mapped[str | None] = mapped_column(ForeignKey("monitors.id", ondelete="SET NULL"), index=True)
    observation_id: Mapped[str | None] = mapped_column(
        ForeignKey("observations.id", ondelete="SET NULL"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(250))
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    dedupe_key: Mapped[str] = mapped_column(String(250), unique=True, default=new_id)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class NotificationDelivery(Record, Base):
    __tablename__ = "notification_deliveries"
    alert_id: Mapped[str] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(30), default="internal")
    recipient: Mapped[str] = mapped_column(String(320), default="")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)


class ThreatIndicator(Record, Base):
    __tablename__ = "threat_indicators"
    __table_args__ = (UniqueConstraint("investigation_id", "indicator_type", "value", "source"),)
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    indicator_type: Mapped[str] = mapped_column(String(60), index=True)
    value: Mapped[str] = mapped_column(String(1024), index=True)
    source: Mapped[str] = mapped_column(String(150))
    source_url: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    data: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class Report(Record, Base):
    __tablename__ = "reports"
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(250))
    format: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)


class AuditLog(Record, Base):
    __tablename__ = "audit_logs"
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    investigation_id: Mapped[str | None] = mapped_column(
        ForeignKey("investigations.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(120), index=True)
    object_type: Mapped[str] = mapped_column(String(80))
    object_id: Mapped[str | None] = mapped_column(String(100))
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class AIAnalysisRun(Record, Base):
    __tablename__ = "ai_analysis_runs"
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    model: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30))
    prompt: Mapped[str] = mapped_column(Text)
    response: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class SocialProfile(Record, Base):
    __tablename__ = "social_profiles"
    __table_args__ = (UniqueConstraint("investigation_id", "platform", "identifier"),)
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    platform: Mapped[str] = mapped_column(String(60))
    identifier: Mapped[str] = mapped_column(String(1024))
    label: Mapped[str] = mapped_column(String(250), default="")
    monitor_id: Mapped[str | None] = mapped_column(ForeignKey("monitors.id", ondelete="SET NULL"), index=True)


class WorkspaceItem(Record, Base):
    __tablename__ = "workspace_items"
    __table_args__ = (CheckConstraint("kind IN ('hypothesis','observation','task')", name="valid_kind"),)
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(30))
    label: Mapped[str] = mapped_column(String(250))
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="open")
