"""Durable one-time administrator bootstrap; existing installations stay closed."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_founder_bootstrap"
down_revision: str | None = "0006_google_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "administrator_bootstrap",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "founder_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.CheckConstraint("id = 1", name=op.f("ck_administrator_bootstrap_singleton")),
    )
    # Never reopen initial-administrator creation for existing/disabled identities,
    # legacy single-role admins, or administrators in the multi-role column.
    op.execute(
        sa.text("""
        INSERT INTO administrator_bootstrap (id, closed_at)
        SELECT 1, CASE WHEN
            EXISTS (SELECT 1 FROM google_identities)
            OR EXISTS (
                SELECT 1 FROM users
                WHERE role = 'platform_admin' OR roles @> '["platform_admin"]'::jsonb
            )
        THEN CURRENT_TIMESTAMP ELSE NULL END
    """)
    )


def downgrade() -> None:
    op.drop_table("administrator_bootstrap")
