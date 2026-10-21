"""Explicit owner-approved reconnection, without losing node history."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0011_worker_reconnection"
down_revision = "0010_account_provider_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("worker_enrollments", sa.Column("replaces_credential_id", UUID(), nullable=True))
    op.create_foreign_key(
        "fk_worker_enrollments_replaces_credential_id_access_credentials",
        "worker_enrollments",
        "access_credentials",
        ["replaces_credential_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_worker_enrollments_replaces_credential_id_access_credentials",
        "worker_enrollments",
        type_="foreignkey",
    )
    op.drop_column("worker_enrollments", "replaces_credential_id")
