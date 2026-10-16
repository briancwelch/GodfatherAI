"""Durable synthetic scheduling, leases, fairness and execution audit."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0003_durable_scheduler"
down_revision: str | None = "0002_worker_health"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("scheduling_turn", sa.BigInteger(), nullable=False, server_default="0")
    )
    op.add_column("jobs", sa.Column("assigned_node_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_jobs_assigned_node_id_nodes",
        "jobs",
        "nodes",
        ["assigned_node_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "jobs", sa.Column("fencing_token", sa.BigInteger(), nullable=False, server_default="0")
    )
    op.add_column(
        "jobs", sa.Column("retry_backoff_seconds", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column("jobs", sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("checkpoint_ref", sa.Text(), nullable=True))
    op.add_column("attempts", sa.Column("session_id", sa.Uuid(), nullable=True))
    op.add_column(
        "attempts", sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("attempts", sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True))
    for field in ("error", "result"):
        op.add_column("attempts", sa.Column(field, JSONB(), nullable=False, server_default="{}"))
    op.create_index(
        "uq_attempts_active_job",
        "attempts",
        ["job_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('ASSIGNED','RUNNING')"),
    )
    op.add_column("events", sa.Column("attempt_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_events_attempt_id_attempts",
        "events",
        "attempts",
        ["attempt_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_events_attempt_id_attempts", "events", type_="foreignkey")
    op.drop_column("events", "attempt_id")
    op.drop_index("uq_attempts_active_job", table_name="attempts")
    for field in ("result", "error", "deadline_at", "acknowledged_at", "session_id"):
        op.drop_column("attempts", field)
    op.drop_constraint("fk_jobs_assigned_node_id_nodes", "jobs", type_="foreignkey")
    for field in (
        "checkpoint_ref",
        "next_run_at",
        "retry_backoff_seconds",
        "fencing_token",
        "assigned_node_id",
    ):
        op.drop_column("jobs", field)
    op.drop_column("users", "scheduling_turn")
