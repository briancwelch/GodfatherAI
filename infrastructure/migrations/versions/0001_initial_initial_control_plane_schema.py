"""Initial control-plane schema"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "capabilities",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_capabilities")),
        sa.UniqueConstraint("name", name=op.f("uq_capabilities_name")),
    )
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=32), server_default="member", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('platform_admin','contributor','member')", name=op.f("ck_users_role")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "models",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("identifier", sa.String(length=300), nullable=False),
        sa.Column(
            "requirements",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_models_owner_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_models")),
    )
    op.create_index(op.f("ix_models_owner_id"), "models", ["owner_id"], unique=False)
    op.create_table(
        "nodes",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("os", sa.String(length=16), nullable=False),
        sa.Column("os_version", sa.String(length=100), nullable=False),
        sa.Column("architecture", sa.String(length=32), nullable=False),
        sa.Column("protocol_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("state", sa.String(length=16), server_default="offline", nullable=False),
        sa.Column(
            "scheduling_policy", sa.String(length=16), server_default="shared", nullable=False
        ),
        sa.Column("concurrency_limit", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "resources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "runtimes", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column(
            "contribution_policy",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("os IN ('windows','macos','linux')", name=op.f("ck_nodes_os")),
        sa.CheckConstraint(
            "scheduling_policy IN ('dedicated','preferred','shared')", name=op.f("ck_nodes_policy")
        ),
        sa.CheckConstraint(
            "state IN ('online','suspect','offline','draining','disabled')",
            name=op.f("ck_nodes_state"),
        ),
        sa.CheckConstraint("concurrency_limit > 0", name=op.f("ck_nodes_concurrency")),
        sa.CheckConstraint("protocol_version > 0", name=op.f("ck_nodes_protocol")),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_nodes_owner_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_nodes")),
    )
    op.create_index(op.f("ix_nodes_owner_id"), "nodes", ["owner_id"], unique=False)
    op.create_table(
        "workspaces",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("is_shared", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_workspaces_owner_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspaces")),
    )
    op.create_index(op.f("ix_workspaces_owner_id"), "workspaces", ["owner_id"], unique=False)
    op.create_table(
        "agents",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "definition",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("version > 0", name=op.f("ck_agents_version")),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_agents_owner_id_users"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_agents_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agents")),
        sa.UniqueConstraint("id", "workspace_id", name="uq_agents_id_workspace"),
        sa.UniqueConstraint(
            "workspace_id", "name", "version", name="uq_agents_workspace_name_version"
        ),
    )
    op.create_index(op.f("ix_agents_owner_id"), "agents", ["owner_id"], unique=False)
    op.create_table(
        "node_capabilities",
        sa.Column("node_id", sa.Uuid(), nullable=False),
        sa.Column("capability_id", sa.Uuid(), nullable=False),
        sa.Column("specialty", sa.String(length=16), server_default="secondary", nullable=False),
        sa.CheckConstraint(
            "specialty IN ('primary','secondary')", name=op.f("ck_node_capabilities_specialty")
        ),
        sa.ForeignKeyConstraint(
            ["capability_id"],
            ["capabilities.id"],
            name=op.f("fk_node_capabilities_capability_id_capabilities"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["node_id"],
            ["nodes.id"],
            name=op.f("fk_node_capabilities_node_id_nodes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("node_id", "capability_id", name=op.f("pk_node_capabilities")),
    )
    op.create_table(
        "node_models",
        sa.Column("node_id", sa.Uuid(), nullable=False),
        sa.Column("model_id", sa.Uuid(), nullable=False),
        sa.Column("runtime", sa.String(length=100), nullable=False),
        sa.Column("backend", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["models.id"],
            name=op.f("fk_node_models_model_id_models"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["node_id"], ["nodes.id"], name=op.f("fk_node_models_node_id_nodes"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("node_id", "model_id", name=op.f("pk_node_models")),
    )
    op.create_table(
        "workspace_members",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), server_default="member", nullable=False),
        sa.CheckConstraint("role IN ('admin','member')", name=op.f("ck_workspace_members_role")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_workspace_members_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_workspace_members_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("workspace_id", "user_id", name=op.f("pk_workspace_members")),
    )
    op.create_table(
        "jobs",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=True),
        sa.Column("type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="PENDING", nullable=False),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), server_default="300", nullable=False),
        sa.Column("retry_limit", sa.Integer(), server_default="0", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "requirements",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "input_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "result_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING','ASSIGNED','RUNNING','RETRY_WAIT',"
            "'COMPLETED','FAILED','CANCELLED')",
            name=op.f("ck_jobs_status"),
        ),
        sa.CheckConstraint("attempt_count >= 0", name=op.f("ck_jobs_attempt_count")),
        sa.CheckConstraint("retry_limit >= 0", name=op.f("ck_jobs_retry_limit")),
        sa.CheckConstraint("timeout_seconds > 0", name=op.f("ck_jobs_timeout")),
        sa.ForeignKeyConstraint(
            ["agent_id", "workspace_id"],
            ["agents.id", "agents.workspace_id"],
            name="fk_jobs_agent_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_jobs_owner_id_users"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_jobs_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
        sa.UniqueConstraint("id", "workspace_id", name="uq_jobs_id_workspace"),
    )
    op.create_index(op.f("ix_jobs_owner_id"), "jobs", ["owner_id"], unique=False)
    op.create_index("ix_jobs_workspace_status", "jobs", ["workspace_id", "status"], unique=False)
    op.create_table(
        "attempts",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("node_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("fencing_token", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="ASSIGNED", nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('ASSIGNED','RUNNING','COMPLETED','FAILED','CANCELLED')",
            name=op.f("ck_attempts_status"),
        ),
        sa.CheckConstraint(
            "number > 0 AND fencing_token > 0", name=op.f("ck_attempts_positive_tokens")
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_attempts_job_id_jobs"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["node_id"], ["nodes.id"], name=op.f("fk_attempts_node_id_nodes"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attempts")),
        sa.UniqueConstraint("id", "job_id", name="uq_attempts_id_job"),
        sa.UniqueConstraint("job_id", "fencing_token", name="uq_attempts_job_fencing"),
        sa.UniqueConstraint("job_id", "number", name="uq_attempts_job_number"),
    )
    op.create_index(op.f("ix_attempts_job_id"), "attempts", ["job_id"], unique=False)
    op.create_table(
        "events",
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("node_id", sa.Uuid(), nullable=True),
        sa.Column("type", sa.String(length=100), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column(
            "details", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name=op.f("fk_events_actor_id_users"), ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "job_id IS NULL OR workspace_id IS NOT NULL", name=op.f("ck_events_job_scope")
        ),
        sa.ForeignKeyConstraint(
            ["job_id", "workspace_id"],
            ["jobs.id", "jobs.workspace_id"],
            name="fk_events_job_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["node_id"], ["nodes.id"], name=op.f("fk_events_node_id_nodes"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_events_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
    )
    op.create_index(op.f("ix_events_correlation_id"), "events", ["correlation_id"], unique=False)
    op.create_index(op.f("ix_events_job_id"), "events", ["job_id"], unique=False)
    op.create_index(op.f("ix_events_workspace_id"), "events", ["workspace_id"], unique=False)
    op.create_table(
        "checkpoints",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("format_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("artifact_ref", sa.Text(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "version > 0 AND format_version > 0", name=op.f("ck_checkpoints_versions")
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id", "job_id"],
            ["attempts.id", "attempts.job_id"],
            name="fk_checkpoints_attempt_job",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_checkpoints_job_id_jobs"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_checkpoints")),
        sa.UniqueConstraint("job_id", "version", name="uq_checkpoints_job_version"),
    )
    op.create_index(op.f("ix_checkpoints_job_id"), "checkpoints", ["job_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_checkpoints_job_id"), table_name="checkpoints")
    op.drop_table("checkpoints")
    op.drop_index(op.f("ix_events_workspace_id"), table_name="events")
    op.drop_index(op.f("ix_events_job_id"), table_name="events")
    op.drop_index(op.f("ix_events_correlation_id"), table_name="events")
    op.drop_table("events")
    op.drop_index(op.f("ix_attempts_job_id"), table_name="attempts")
    op.drop_table("attempts")
    op.drop_index("ix_jobs_workspace_status", table_name="jobs")
    op.drop_index(op.f("ix_jobs_owner_id"), table_name="jobs")
    op.drop_table("jobs")
    op.drop_table("workspace_members")
    op.drop_table("node_models")
    op.drop_table("node_capabilities")
    op.drop_index(op.f("ix_agents_owner_id"), table_name="agents")
    op.drop_table("agents")
    op.drop_index(op.f("ix_workspaces_owner_id"), table_name="workspaces")
    op.drop_table("workspaces")
    op.drop_index(op.f("ix_nodes_owner_id"), table_name="nodes")
    op.drop_table("nodes")
    op.drop_index(op.f("ix_models_owner_id"), table_name="models")
    op.drop_table("models")
    op.drop_table("users")
    op.drop_table("capabilities")
