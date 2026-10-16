"""Versioned agents, durable workflow metadata and immutable artifact references."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0004_agent_runtime"
down_revision: str | None = "0003_durable_scheduler"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("agent_key", sa.Uuid(), nullable=True))
    op.execute("UPDATE agents SET agent_key = id")
    op.alter_column(
        "agents", "agent_key", nullable=False, server_default=sa.text("gen_random_uuid()")
    )
    op.add_column(
        "agents", sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false")
    )
    op.create_unique_constraint(
        "uq_agents_key_version", "agents", ["workspace_id", "agent_key", "version"]
    )
    op.create_table(
        "artifacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.UniqueConstraint("id", "job_id", name="uq_artifacts_id_job"),
        sa.ForeignKeyConstraint(
            ["attempt_id", "job_id"],
            ["attempts.id", "attempts.job_id"],
            name="fk_artifacts_attempt_job",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["job_id", "workspace_id"],
            ["jobs.id", "jobs.workspace_id"],
            name="fk_artifacts_job_workspace",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("size_bytes > 0 AND size_bytes <= 262144", name="size"),
        sa.CheckConstraint("kind IN ('step_output','workflow_state')", name="kind"),
    )
    op.create_index("ix_artifacts_owner_id", "artifacts", ["owner_id"])
    op.create_index("ix_artifacts_job_id", "artifacts", ["job_id"])
    op.add_column("checkpoints", sa.Column("artifact_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_checkpoints_artifact_job",
        "checkpoints",
        "artifacts",
        ["artifact_id", "job_id"],
        ["id", "job_id"],
        ondelete="RESTRICT",
    )
    op.create_table(
        "workflow_runs",
        sa.Column(
            "job_id", sa.Uuid(), sa.ForeignKey("jobs.id", ondelete="RESTRICT"), primary_key=True
        ),
        sa.Column(
            "agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_version", sa.Integer(), nullable=False),
        sa.Column("cursor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checkpoint_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="READY"),
        sa.Column("recovery_node_id", sa.Uuid(), sa.ForeignKey("nodes.id", ondelete="RESTRICT")),
        sa.CheckConstraint(
            "cursor >= 0 AND cursor <= 32 AND checkpoint_version = cursor", name="cursor"
        ),
        sa.CheckConstraint(
            "status IN ('READY','RUNNING','INTERRUPTED','COMPLETED','FAILED','CANCELLED')",
            name="status",
        ),
    )
    op.create_table(
        "workflow_steps",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "job_id", sa.Uuid(), sa.ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.String(100), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="RUNNING"),
        sa.Column("input_refs", JSONB(), nullable=False, server_default="{}"),
        sa.Column("output_artifact_id", sa.Uuid(), nullable=True),
        sa.Column("metadata_refs", JSONB(), nullable=False, server_default="{}"),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["attempt_id", "job_id"],
            ["attempts.id", "attempts.job_id"],
            name="fk_workflow_steps_attempt_job",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["output_artifact_id", "job_id"],
            ["artifacts.id", "artifacts.job_id"],
            name="fk_workflow_steps_output_job",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("job_id", "step_id", "attempt_id", name="uq_workflow_steps_attempt"),
        sa.CheckConstraint(
            "status IN ('RUNNING','COMPLETED','INTERRUPTED','FAILED','CANCELLED')", name="status"
        ),
    )
    op.create_index("ix_workflow_steps_job_id", "workflow_steps", ["job_id"])
    op.create_index(
        "uq_workflow_steps_completed",
        "workflow_steps",
        ["job_id", "step_id"],
        unique=True,
        postgresql_where=sa.text("status = 'COMPLETED'"),
    )


def downgrade() -> None:
    op.drop_table("workflow_steps")
    op.drop_table("workflow_runs")
    op.drop_constraint("fk_checkpoints_artifact_job", "checkpoints", type_="foreignkey")
    op.drop_column("checkpoints", "artifact_id")
    op.drop_table("artifacts")
    op.drop_constraint("uq_agents_key_version", "agents", type_="unique")
    op.drop_column("agents", "enabled")
    op.drop_column("agents", "agent_key")
