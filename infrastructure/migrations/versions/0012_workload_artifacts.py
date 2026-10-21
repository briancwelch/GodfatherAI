"""Increase the bounded immutable artifact envelope for images and reports.

Revision ID: 0012_workload_artifacts
Revises: 0011_worker_reconnection
"""

from alembic import op

revision = "0012_workload_artifacts"
down_revision = "0011_worker_reconnection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_artifacts_size"), "artifacts", type_="check")
    op.create_check_constraint(
        op.f("ck_artifacts_size"), "artifacts", "size_bytes > 0 AND size_bytes <= 8388608"
    )


def downgrade() -> None:
    # Refuse rather than truncate/delete larger artifacts when rolling back.
    op.drop_constraint(op.f("ck_artifacts_size"), "artifacts", type_="check")
    op.create_check_constraint(
        op.f("ck_artifacts_size"), "artifacts", "size_bytes > 0 AND size_bytes <= 262144"
    )
