"""Remove managed setups without losing history or allowing stale advertisements."""

import sqlalchemy as sa
from alembic import op

revision = "0018_shared_engine_removal"
down_revision = "0017_shared_engine_setup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("shared_engine_setups", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.add_column(
        "shared_engine_consents",
        sa.Column("dismissed", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("shared_engine_consents", "dismissed")
    op.drop_column("shared_engine_setups", "deleted_at")
