"""Node credentials, process sessions and independent connection health."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_worker_health"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "nodes",
        sa.Column("connection_status", sa.String(16), nullable=False, server_default="offline"),
    )
    op.add_column("nodes", sa.Column("session_id", sa.Uuid(), nullable=True))
    op.create_check_constraint(
        op.f("ck_nodes_connection"), "nodes", "connection_status IN ('online','suspect','offline')"
    )
    op.create_table(
        "access_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(100), nullable=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("node_id", sa.Uuid(), nullable=True),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_access_credentials"),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_access_credentials_owner_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["node_id"],
            ["nodes.id"],
            ondelete="RESTRICT",
            name="fk_access_credentials_node_id_nodes",
        ),
        sa.UniqueConstraint("token_hash", name="uq_access_credentials_token_hash"),
        sa.UniqueConstraint("node_id", name="uq_access_credentials_node_id"),
        sa.UniqueConstraint("owner_id", "name", name="uq_credentials_owner_name"),
        sa.CheckConstraint("kind IN ('admin','worker')", name=op.f("ck_access_credentials_kind")),
        sa.CheckConstraint(
            "(kind='admin' AND name IS NULL AND node_id IS NULL) OR "
            "(kind='worker' AND name IS NOT NULL)",
            name=op.f("ck_access_credentials_scope"),
        ),
    )
    op.create_index("ix_access_credentials_owner_id", "access_credentials", ["owner_id"])


def downgrade() -> None:
    op.drop_table("access_credentials")
    op.drop_constraint(op.f("ck_nodes_connection"), "nodes", type_="check")
    op.drop_column("nodes", "session_id")
    op.drop_column("nodes", "connection_status")
