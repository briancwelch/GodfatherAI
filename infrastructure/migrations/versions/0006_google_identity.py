"""Google identities, opaque sessions and invitation-only onboarding; preserve user UUIDs."""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0006_google_identity"
down_revision: str | None = "0005_cross_node_recovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def entity() -> list[sa.Column[Any]]:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    ]


def user_ref(name: str, **kwargs: Any) -> sa.Column[Any]:
    return sa.Column(name, sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), **kwargs)


def upgrade() -> None:
    # NULL retains existing local read-only grants; newly created workspaces use
    # explicit empty allowlists until their owner grants models/tools.
    op.add_column("workspaces", sa.Column("allowed_models", JSONB(), nullable=True))
    op.add_column("workspaces", sa.Column("allowed_tools", JSONB(), nullable=True))
    op.add_column("users", sa.Column("roles", JSONB(), nullable=False, server_default="[]"))
    op.add_column("users", sa.Column("picture", sa.String(2048), nullable=True))
    op.create_table(
        "google_identities",
        *entity(),
        user_ref("user_id", nullable=False, unique=True),
        sa.Column("subject", sa.String(255), nullable=False, unique=True),
    )
    op.create_table(
        "human_sessions",
        *entity(),
        user_ref("owner_id", nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index("ix_human_sessions_owner_id", "human_sessions", ["owner_id"])
    op.create_index("ix_human_sessions_expires_at", "human_sessions", ["expires_at"])
    op.create_table(
        "invitations",
        *entity(),
        user_ref("actor_id", nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("roles", JSONB(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default="false"),
        user_ref("used_by", nullable=True),
    )
    op.create_table(
        "login_transactions",
        *entity(),
        sa.Column("state_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("browser_hash", sa.String(64), nullable=False),
        sa.Column("nonce", sa.String(128), nullable=False),
        sa.Column("verifier", sa.String(128), nullable=False),
        sa.Column("invitation_id", sa.Uuid(), sa.ForeignKey("invitations.id")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index("ix_login_transactions_expires_at", "login_transactions", ["expires_at"])
    op.create_table(
        "authentication_limits",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("window", sa.BigInteger(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("workspaces", "allowed_tools")
    op.drop_column("workspaces", "allowed_models")
    for table in (
        "authentication_limits",
        "login_transactions",
        "invitations",
        "human_sessions",
        "google_identities",
    ):
        op.drop_table(table)
    op.drop_column("users", "picture")
    op.drop_column("users", "roles")
