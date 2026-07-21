"""Initial Orchestra schema.

Revision ID: 001_initial
Creates all tables and the NOTIFY trigger for live WebSocket updates.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- workflows ---
    op.create_table(
        "workflows",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text()),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("current_version", sa.Integer(), default=1),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- workflow_versions ---
    op.create_table(
        "workflow_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workflow_id", sa.String(64), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("published_by", sa.String(255)),
        sa.UniqueConstraint("workflow_id", "version", name="uq_workflow_version"),
    )

    # --- runs ---
    op.create_table(
        "runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workflow_id", sa.String(64), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workflow_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.Enum("pending", "running", "paused", "succeeded", "failed", name="runstatus"), default="pending"),
        sa.Column("trigger_input", sa.JSON()),
        sa.Column("triggered_by", sa.String(255)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_runs_workflow_status", "runs", ["workflow_id", "status"])

    # --- tasks ---
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_key", sa.String(255), nullable=False),
        sa.Column("task_type", sa.String(255), nullable=False),
        sa.Column("status", sa.Enum(
            "pending", "claimed", "running", "checkpointing",
            "succeeded", "failed", "dead_letter", "skipped",
            name="taskstatus",
        ), default="pending"),
        sa.Column("priority", sa.Integer(), default=0),
        sa.Column("run_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("max_attempts", sa.Integer(), default=3),
        sa.Column("current_attempt", sa.Integer(), default=0),
        sa.Column("depends_on", sa.JSON()),
        sa.Column("input_data", sa.JSON()),
        sa.Column("output_data", sa.JSON()),
        sa.Column("error_detail", sa.Text()),
        sa.Column("lease_id", sa.String(64)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("worker_id", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("run_id", "task_key", name="uq_run_task_key"),
    )
    op.create_index("idx_tasks_status_run_at", "tasks", ["status", "run_at"])

    # --- task_attempts ---
    op.create_table(
        "task_attempts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("task_id", sa.String(64), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("worker_id", sa.String(255)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("input_snapshot", sa.JSON()),
        sa.Column("output_snapshot", sa.JSON()),
        sa.Column("error_detail", sa.Text()),
        sa.Column("duration_ms", sa.BigInteger()),
        sa.UniqueConstraint("task_id", "attempt_number", name="uq_attempt_number"),
    )

    # --- checkpoints ---
    op.create_table(
        "checkpoints",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("attempt_id", sa.String(64), sa.ForeignKey("task_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step", sa.String(255), nullable=False),
        sa.Column("data", sa.JSON()),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("attempt_id", "step", name="uq_checkpoint_step"),
    )

    # --- audit_log ---
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("from_status", sa.String(64)),
        sa.Column("to_status", sa.String(64)),
        sa.Column("actor", sa.String(255)),
        sa.Column("metadata", sa.JSON()),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("prev_hash", sa.String(64)),
    )
    op.create_index("idx_audit_entity", "audit_log", ["entity_type", "entity_id"])

    # --- refresh_tokens ---
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), default=False),
        sa.Column("revoked", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- NOTIFY trigger for live WebSocket updates ---
    # Fires on every task status update, sends payload to WS gateway via LISTEN/NOTIFY
    op.execute("""
        CREATE OR REPLACE FUNCTION notify_task_state_change()
        RETURNS trigger AS $$
        DECLARE
            payload json;
        BEGIN
            payload = json_build_object(
                'event', 'task.state_changed',
                'run_id', NEW.run_id,
                'task_id', NEW.id,
                'task_key', NEW.task_key,
                'from', OLD.status,
                'to', NEW.status,
                'attempt', NEW.current_attempt,
                'at', now()
            );
            PERFORM pg_notify('task_state_changes', payload::text);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER task_state_change_notify
        AFTER UPDATE OF status ON tasks
        FOR EACH ROW
        WHEN (OLD.status IS DISTINCT FROM NEW.status)
        EXECUTE FUNCTION notify_task_state_change();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS task_state_change_notify ON tasks")
    op.execute("DROP FUNCTION IF EXISTS notify_task_state_change")
    op.drop_table("refresh_tokens")
    op.drop_table("audit_log")
    op.drop_table("checkpoints")
    op.drop_table("task_attempts")
    op.drop_table("tasks")
    op.drop_table("runs")
    op.drop_table("workflow_versions")
    op.drop_table("workflows")
    op.execute("DROP TYPE IF EXISTS taskstatus")
    op.execute("DROP TYPE IF EXISTS runstatus")
