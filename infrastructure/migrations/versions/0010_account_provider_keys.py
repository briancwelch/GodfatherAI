"""Owner-scoped encrypted account credentials; preserve existing local connections."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0010_account_provider_keys"
down_revision = "0009_provider_connections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_provider_keys",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "owner_id", UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("encrypted_key", sa.Text(), nullable=False),
        sa.Column("model_catalog", JSONB(), server_default="[]", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("allowed_node_ids", JSONB(), server_default="[]", nullable=False),
        sa.UniqueConstraint("owner_id", "provider", name="uq_account_provider_owner"),
    )
    op.create_index("ix_account_provider_keys_owner_id", "account_provider_keys", ["owner_id"])
    op.add_column("provider_connections", sa.Column("account_key_id", UUID(), nullable=True))
    op.create_foreign_key(
        "fk_provider_connections_account_key_id_account_provider_keys",
        "provider_connections",
        "account_provider_keys",
        ["account_key_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_provider_account_node", "provider_connections", ["account_key_id", "node_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_provider_account_node", "provider_connections", type_="unique")
    op.drop_constraint(
        "fk_provider_connections_account_key_id_account_provider_keys",
        "provider_connections",
        type_="foreignkey",
    )
    op.drop_column("provider_connections", "account_key_id")
    op.drop_index("ix_account_provider_keys_owner_id", table_name="account_provider_keys")
    op.drop_table("account_provider_keys")
