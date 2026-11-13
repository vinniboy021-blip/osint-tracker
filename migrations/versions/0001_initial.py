"""initial relational schema"""
import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> sa.text:
    return sa.text("NOW() AT TIME ZONE 'UTC'")


# ---------------------------------------------------------------------------
# upgrade / downgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    # users
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("hashed_password", sa.Text, nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="viewer"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_utcnow()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_utcnow()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # sessions
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_utcnow()),
    )
    op.create_index("ix_sessions_token_hash", "sessions", ["token_hash"], unique=True)
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    # investigations
    op.create_table(
        "investigations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("objective", sa.Text, nullable=True),
        sa.Column("scope", sa.Text, nullable=True),
        sa.Column("authorization_basis", sa.Text, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_utcnow()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_utcnow()),
    )
    op.create_index("ix_investigations_owner_id", "investigations", ["owner_id"])

    # investigation_members
    op.create_table(
        "investigation_members",
        sa.Column("investigation_id", sa.String(36), sa.ForeignKey("investigations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.String(32), nullable=False, server_default="viewer"),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=_utcnow()),
    )

    # connectors
    op.create_table(
        "connectors",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_health_check", sa.DateTime(timezone=True), nullable=True),
        sa.Column("health_status", sa.String(32), nullable=True),
    )

    # connector_configurations
    op.create_table(
        "connector_configurations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("connector_id", sa.String(64), sa.ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("encrypted_config", sa.Text, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_utcnow()),
    )

    # collection_jobs
    op.create_table(
        "collection_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("investigation_id", sa.String(36), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connector_id", sa.String(64), sa.ForeignKey("connectors.id"), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("monitor_id", sa.String(36), nullable=True),
        sa.Column("idempotency_key", sa.String(64), nullable=False, unique=True),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("config", sa.JSON, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_utcnow()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
    )
    op.create_index("ix_collection_jobs_investigation_id", "collection_jobs", ["investigation_id"])
    op.create_index("ix_collection_jobs_status", "collection_jobs", ["status"])

    # observations
    op.create_table(
        "observations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("investigation_id", sa.String(36), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("collection_jobs.id"), nullable=True),
        sa.Column("connector_id", sa.String(64), nullable=False),
        sa.Column("external_id", sa.String(512), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column("data", sa.JSON, nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False, server_default=_utcnow()),
    )
    op.create_index("ix_observations_investigation_id", "observations", ["investigation_id"])
    op.create_index("ix_observations_fingerprint", "observations", ["fingerprint"])

    # entities
    op.create_table(
        "entities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("investigation_id", sa.String(36), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("metadata", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_utcnow()),
    )
    op.create_index("ix_entities_investigation_id", "entities", ["investigation_id"])

    # monitors
    op.create_table(
        "monitors",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("investigation_id", sa.String(36), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connector_id", sa.String(64), sa.ForeignKey("connectors.id"), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("config", sa.JSON, nullable=True),
        sa.Column("schedule_type", sa.String(16), nullable=False),
        sa.Column("interval_seconds", sa.Integer, nullable=True),
        sa.Column("cron_expression", sa.String(64), nullable=True),
        sa.Column("paused", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_utcnow()),
    )
    op.create_index("ix_monitors_investigation_id", "monitors", ["investigation_id"])

    # evidence
    op.create_table(
        "evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("investigation_id", sa.String(36), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploaded_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("storage_key", sa.String(32), nullable=False, unique=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_utcnow()),
    )
    op.create_index("ix_evidence_investigation_id", "evidence", ["investigation_id"])

    # evidence_versions
    op.create_table(
        "evidence_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("evidence_id", sa.String(36), sa.ForeignKey("evidence.id", ondelete="CASCADE"), nullable=False),
        sa.Column("storage_key", sa.String(32), nullable=False, unique=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_utcnow()),
    )
    op.create_index("ix_evidence_versions_evidence_id", "evidence_versions", ["evidence_id"])

    # alerts
    op.create_table(
        "alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("investigation_id", sa.String(36), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("monitor_id", sa.String(36), nullable=True),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("read", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_utcnow()),
    )
    op.create_index("ix_alerts_investigation_id", "alerts", ["investigation_id"])

    # audit_logs
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("investigation_id", sa.String(36), nullable=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("object_type", sa.String(64), nullable=True),
        sa.Column("object_id", sa.String(36), nullable=True),
        sa.Column("details", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_utcnow()),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_investigation_id", "audit_logs", ["investigation_id"])

    # threat_indicators
    op.create_table(
        "threat_indicators",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("investigation_id", sa.String(36), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("added_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("confidence", sa.String(16), nullable=True),
        sa.Column("tags", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_utcnow()),
    )
    op.create_index("ix_threat_indicators_kind_value", "threat_indicators", ["kind", "value"])

    # correlations
    op.create_table(
        "correlations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("investigation_id", sa.String(36), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_a_id", sa.String(36), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_b_id", sa.String(36), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relationship", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("status", sa.String(32), nullable=False, server_default="unverified"),
        sa.Column("review_note", sa.Text, nullable=True),
        sa.Column("reviewed_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_utcnow()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_utcnow()),
    )
    op.create_index("ix_correlations_investigation_id", "correlations", ["investigation_id"])

    # workspace_items
    op.create_table(
        "workspace_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("investigation_id", sa.String(36), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_utcnow()),
    )
    op.create_index("ix_workspace_items_investigation_id", "workspace_items", ["investigation_id"])

    # reports
    op.create_table(
        "reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("investigation_id", sa.String(36), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("format", sa.String(16), nullable=False),
        sa.Column("storage_key", sa.String(32), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_utcnow()),
    )
    op.create_index("ix_reports_investigation_id", "reports", ["investigation_id"])

    # ai_runs
    op.create_table(
        "ai_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("investigation_id", sa.String(36), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("hypotheses", sa.JSON, nullable=True),
        sa.Column("citations", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_utcnow()),
    )
    op.create_index("ix_ai_runs_investigation_id", "ai_runs", ["investigation_id"])

    # social_profiles
    op.create_table(
        "social_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("investigation_id", sa.String(36), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("platform", sa.String(64), nullable=False),
        sa.Column("handle", sa.String(255), nullable=False),
        sa.Column("monitor_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_utcnow()),
    )
    op.create_index("ix_social_profiles_investigation_id", "social_profiles", ["investigation_id"])


def downgrade() -> None:
    op.drop_table("social_profiles")
    op.drop_table("ai_runs")
    op.drop_table("reports")
    op.drop_table("workspace_items")
    op.drop_table("correlations")
    op.drop_table("threat_indicators")
    op.drop_table("audit_logs")
    op.drop_table("alerts")
    op.drop_table("evidence_versions")
    op.drop_table("evidence")
    op.drop_table("monitors")
    op.drop_table("entities")
    op.drop_table("observations")
    op.drop_table("collection_jobs")
    op.drop_table("connector_configurations")
    op.drop_table("connectors")
    op.drop_table("investigation_members")
    op.drop_table("investigations")
    op.drop_table("sessions")
    op.drop_index("ix_users_email", "users")
    op.drop_table("users")
