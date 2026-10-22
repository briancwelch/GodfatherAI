"""Owner-managed account profile preferences."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015_account_profile"
down_revision = "0014_command_center_appearance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("profile", postgresql.JSONB(), nullable=False, server_default="{}")
    )


def downgrade() -> None:
    op.drop_column("users", "profile")
