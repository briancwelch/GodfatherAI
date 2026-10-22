"""Retain durable history while removing deleted Command Center records from use."""

import sqlalchemy as sa
from alembic import op

revision = "0013_command_center_deletion"
down_revision = "0012_workload_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("workspaces", "agents", "jobs"):
        op.add_column(table, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for table in ("jobs", "agents", "workspaces"):
        op.drop_column(table, "deleted_at")
