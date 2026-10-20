"""Independent metadata-only provider credentials, grants and usage reservations.

Revision ID: 0009_provider_connections
Revises: 0008_worker_enrollment
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0009_provider_connections"
down_revision = "0008_worker_enrollment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_connections",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "owner_id", UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "node_id", UUID(), sa.ForeignKey("nodes.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("policy", JSONB(), server_default="{}", nullable=False),
        sa.Column("revoked", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("test_id", UUID(), nullable=True),
        sa.Column("test_result", JSONB(), server_default="{}", nullable=False),
    )
    op.create_index("ix_provider_connections_owner_id", "provider_connections", ["owner_id"])
    op.create_table(
        "provider_connection_grants",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "connection_id",
            UUID(),
            sa.ForeignKey("provider_connections.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "owner_id", UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("scope", JSONB(), nullable=False),
        sa.Column("revoked", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_index(
        "ix_provider_connection_grants_connection_id",
        "provider_connection_grants",
        ["connection_id"],
    )
    op.create_table(
        "provider_invocations",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "connection_id",
            UUID(),
            sa.ForeignKey("provider_connections.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "grant_id", UUID(), sa.ForeignKey("provider_connection_grants.id", ondelete="RESTRICT")
        ),
        sa.Column("job_id", UUID(), sa.ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column(
            "attempt_id", UUID(), sa.ForeignKey("attempts.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "payer_id", UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "submitter_id", UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("call_key", sa.String(100), nullable=False),
        sa.Column("reserved_microusd", sa.BigInteger(), nullable=False),
        sa.Column("settled_microusd", sa.BigInteger()),
        sa.Column("price", JSONB(), nullable=False),
        sa.Column("usage", JSONB(), server_default="{}", nullable=False),
        sa.Column("status", sa.String(32), server_default="reserved", nullable=False),
        sa.UniqueConstraint("attempt_id", "call_key", name="uq_provider_invocation_call"),
    )
    op.create_index(
        "ix_provider_invocations_connection_id", "provider_invocations", ["connection_id"]
    )
    op.create_index("ix_provider_invocations_job_id", "provider_invocations", ["job_id"])


def downgrade() -> None:
    op.drop_table("provider_invocations")
    op.drop_table("provider_connection_grants")
    op.drop_table("provider_connections")
