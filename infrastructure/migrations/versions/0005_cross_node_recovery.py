"""Cross-node interruption history and fail-closed restoration review."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_cross_node_recovery"
down_revision: str | None = "0004_agent_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_attempts_status"), "attempts", type_="check")
    op.create_check_constraint(
        op.f("ck_attempts_status"),
        "attempts",
        "status IN ('ASSIGNED','RUNNING','COMPLETED','FAILED','CANCELLED','INTERRUPTED')",
    )
    op.add_column("attempts", sa.Column("recovered_from_attempt_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_attempts_recovered_from_attempt_id_attempts",
        "attempts",
        "attempts",
        ["recovered_from_attempt_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "attempts",
        sa.Column("resumed_checkpoint_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("workflow_runs", sa.Column("recovery_error", sa.String(64), nullable=True))
    op.drop_constraint(op.f("ck_workflow_runs_status"), "workflow_runs", type_="check")
    op.create_check_constraint(
        op.f("ck_workflow_runs_status"),
        "workflow_runs",
        "status IN ('READY','RUNNING','INTERRUPTED','COMPLETED','FAILED',"
        "'CANCELLED','REVIEW_REQUIRED')",
    )


def downgrade() -> None:
    # Only run against an explicitly approved rollback or disposable test database.
    op.execute("UPDATE attempts SET status='FAILED' WHERE status='INTERRUPTED'")
    op.execute("UPDATE workflow_runs SET status='INTERRUPTED' WHERE status='REVIEW_REQUIRED'")
    op.drop_constraint(op.f("ck_workflow_runs_status"), "workflow_runs", type_="check")
    op.create_check_constraint(
        op.f("ck_workflow_runs_status"),
        "workflow_runs",
        "status IN ('READY','RUNNING','INTERRUPTED','COMPLETED','FAILED','CANCELLED')",
    )
    op.drop_column("workflow_runs", "recovery_error")
    op.drop_column("attempts", "resumed_checkpoint_version")
    op.drop_constraint(
        "fk_attempts_recovered_from_attempt_id_attempts", "attempts", type_="foreignkey"
    )
    op.drop_column("attempts", "recovered_from_attempt_id")
    op.drop_constraint(op.f("ck_attempts_status"), "attempts", type_="check")
    op.create_check_constraint(
        op.f("ck_attempts_status"),
        "attempts",
        "status IN ('ASSIGNED','RUNNING','COMPLETED','FAILED','CANCELLED')",
    )
