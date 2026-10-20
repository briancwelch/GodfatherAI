"""Add short-lived, owner-approved worker pairing grants."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_worker_enrollment"
down_revision: str | None = "0007_founder_bootstrap"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "worker_enrollments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("challenge", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_index("ix_worker_enrollments_owner_id", "worker_enrollments", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_worker_enrollments_owner_id", table_name="worker_enrollments")
    op.drop_table("worker_enrollments")
