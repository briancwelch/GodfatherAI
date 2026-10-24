"""Durable per-node owner consent for managed shared inference."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0017_shared_engine_setup"
down_revision = "0016_distributed_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shared_engine_setups",
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
        sa.Column(
            "leader_node_id",
            sa.Uuid(),
            sa.ForeignKey("nodes.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("proposal", pg.JSONB(), nullable=False),
        sa.Column("desired_running", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("generation", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_index("ix_shared_engine_setups_owner_id", "shared_engine_setups", ["owner_id"])
    op.create_index(
        "ix_shared_engine_setups_workspace_id", "shared_engine_setups", ["workspace_id"]
    )
    op.create_table(
        "shared_engine_consents",
        sa.Column(
            "group_id",
            sa.Uuid(),
            sa.ForeignKey("shared_engine_setups.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "node_id", sa.Uuid(), sa.ForeignKey("nodes.id", ondelete="RESTRICT"), primary_key=True
        ),
        sa.Column(
            "credential_id", sa.Uuid(), sa.ForeignKey("access_credentials.id", ondelete="RESTRICT")
        ),
        sa.Column("approved", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("configuration", pg.JSONB(), server_default="{}", nullable=False),
        sa.Column("phase", sa.String(16), server_default="waiting", nullable=False),
        sa.Column("error_code", sa.String(64)),
    )
    op.create_index("ix_shared_engine_consents_node_id", "shared_engine_consents", ["node_id"])


def downgrade() -> None:
    op.drop_table("shared_engine_consents")
    op.drop_table("shared_engine_setups")
