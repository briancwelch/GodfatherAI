"""Persistent distributed parents and membership of existing fenced jobs."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0016_distributed_jobs"
down_revision = "0015_account_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "distributed_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspaces.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("selected_node_ids", pg.JSONB(), nullable=False),
        sa.Column("final_task", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("error", sa.String(200)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('PENDING','RUNNING','COMPLETED','FAILED','CANCELLED')", name="status"
        ),
    )
    op.create_index("ix_distributed_jobs_owner_id", "distributed_jobs", ["owner_id"])
    op.create_index(
        "ix_distributed_jobs_workspace_created", "distributed_jobs", ["workspace_id", "created_at"]
    )
    op.create_table(
        "distributed_tasks",
        sa.Column(
            "job_id", sa.Uuid(), sa.ForeignKey("jobs.id", ondelete="RESTRICT"), primary_key=True
        ),
        sa.Column(
            "distributed_job_id",
            sa.Uuid(),
            sa.ForeignKey("distributed_jobs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("depends_on", pg.JSONB(), nullable=False),
        sa.Column("allowed_node_ids", pg.JSONB(), nullable=False),
        sa.Column("ready", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("distributed_job_id", "key"),
    )
    op.create_index(
        "ix_distributed_tasks_distributed_job_id", "distributed_tasks", ["distributed_job_id"]
    )


def downgrade() -> None:
    op.drop_table("distributed_tasks")
    op.drop_table("distributed_jobs")
