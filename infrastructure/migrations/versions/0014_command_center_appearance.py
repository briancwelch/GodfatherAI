"""Persist site appearance and retain deleted machine credential history."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014_command_center_appearance"
down_revision = "0013_command_center_deletion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "access_credentials", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_table(
        "application_settings",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", postgresql.JSONB(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("application_settings")
    op.drop_column("access_credentials", "deleted_at")
